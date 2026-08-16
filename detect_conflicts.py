from normalize import safe_normalize, make_data_error
from warehouse_client import WAREHOUSE_CLIENTS

ALL_SOURCES = ["A", "B", "C"]

def get_combined_stock():
    """Read all warehouses and return (usable_records, data_errors).

    A warehouse that can't be reached, or a record that can't be used, becomes
    a data_error instead of stopping the run.
    """
    combined = []
    errors = []

    for source in ALL_SOURCES:
        client = WAREHOUSE_CLIENTS[source]

        try:
            raw_records = client.list_stock()
        except Exception as e:
            # covers service down, timeout, HTTP errors and bad responses
            detail = f"could not read warehouse {source}: {e}"
            errors.append(make_data_error(source, "ALL", detail, "", scope="source"))
            continue

        for record in raw_records:
            normalized, error = safe_normalize(record, source)
            if error:
                errors.append(error)
                continue
            normalized["source"] = source
            combined.append(normalized)

    return combined, errors

def detect_conflicts(combined, data_errors=None):
    """Find all conflicts. Data errors are passed in and counted as conflicts."""
    conflicts = list(data_errors or [])

    # Warehouses we couldn't read. Don't compare against these - we don't know
    # what they hold, so a missing SKU would be a guess.
    unavailable = {e["source"] for e in conflicts if e.get("scope") == "source"}
    comparable_sources = [s for s in ALL_SOURCES if s not in unavailable]

    # Same for single records we couldn't read: sku -> sources it was broken in
    broken_records = {}
    for e in conflicts:
        if e.get("scope") == "record" and e["sku"] != "UNKNOWN":
            broken_records.setdefault(e["sku"], set()).add(e["source"])

    # group entries by sku
    by_sku = {}
    for entry in combined:
        by_sku.setdefault(entry["sku"], []).append(entry)

    for sku, entries in by_sku.items():
        sources_present = [e["source"] for e in entries]
        qtys = [e["qty"] for e in entries]

        # missing from one or more systems
        unreadable_here = broken_records.get(sku, set())
        missing_from = [
            s for s in comparable_sources
            if s not in sources_present and s not in unreadable_here
        ]
        if missing_from:
            conflicts.append({
                "sku": sku,
                "type": "missing_sku",
                "missing_from": missing_from,
                "present_in": sources_present,
            })

        # negative stock (overselling)
        has_negative_stock = False
        for e in entries:
            if e["qty"] < 0:
                has_negative_stock = True
                conflicts.append({
                    "sku": sku,
                    "type": "negative_stock",
                    "source": e["source"],
                    "qty": e["qty"],
                })

        # quantity mismatch. Skipped when the SKU already has negative stock,
        # since a negative value always looks like a mismatch too.
        if len(set(qtys)) > 1 and not has_negative_stock:
            mismatch = {
                "sku": sku,
                "type": "quantity_mismatch",
                "values": {e["source"]: e["qty"] for e in entries},
            }

            # Note any source we couldn't read, so decide.py can tell a real
            # disagreement from a missing opinion. Only added when non-empty,
            # to keep the fingerprint of a normal mismatch unchanged.
            couldnt_ask = sorted(unavailable | unreadable_here)
            if couldnt_ask:
                mismatch["unavailable_sources"] = couldnt_ask

            conflicts.append(mismatch)

    return conflicts


if __name__ == "__main__":
    combined, data_errors = get_combined_stock()
    conflicts = detect_conflicts(combined, data_errors)
    for c in conflicts:
        print(c)
