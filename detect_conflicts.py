from normalize import safe_normalize, make_data_error
from warehouse_client import WAREHOUSE_CLIENTS

ALL_SOURCES = ["A", "B", "C"]

def get_combined_stock():
    """Read every warehouse and return (usable_records, data_errors).

    Failures are contained at two levels:
      - the whole source (service down, timeout, HTTP error, junk response)
      - a single record inside an otherwise fine source

    Either way the agent records the problem and keeps going. Aborting the run
    would mean one bad row in one warehouse blocks every unrelated fix in the
    other two, which is the opposite of what a sync agent is for.
    """
    combined = []
    errors = []

    for source in ALL_SOURCES:
        client = WAREHOUSE_CLIENTS[source]

        try:
            raw_records = client.list_stock()
        except Exception as e:
            # Broad on purpose: this is the boundary with a foreign system, and
            # every failure mode behind it (service down, timeout, 500, junk
            # response) has the same correct response — note it and move on.
            # This block did not change when the warehouses moved from local
            # imports to HTTP services; a network failure arrives here exactly
            # the way an unreadable file used to.
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
    # Data errors are already conflicts — they just came from the reading stage
    # rather than the comparing stage, so they start the list.
    conflicts = list(data_errors or [])

    # If a whole warehouse failed to answer, we cannot conclude anything about
    # what it stocks. Without this, one unreadable warehouse would report every
    # SKU in the system as "missing from C", when the truth is "we couldn't ask
    # C". That would bury the one real problem under a pile of invented ones.
    unavailable = {e["source"] for e in conflicts if e.get("scope") == "source"}
    comparable_sources = [s for s in ALL_SOURCES if s not in unavailable]

    # Same reasoning one level down. If warehouse C holds a record for SKU-001
    # but that record is unusable, "missing from C" is simply untrue — C has it,
    # we just can't read it. That SKU is already flagged as a data_error, so
    # reporting it as missing too would send someone looking for the wrong thing.
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

        # conflict type 1: missing from one or more systems
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

        # conflict type 2: negative stock (overselling)
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

        # conflict type 3: quantity mismatch between systems that have it
        #
        # Deliberately suppressed when this SKU already has a negative_stock
        # conflict. A negative quantity is guaranteed to also look like a
        # mismatch (nobody else is reporting -3), so reporting both means
        # reporting the same incident twice. The negative stock is the root
        # cause and its fix — a physical recount — resolves the mismatch too,
        # so acting on the mismatch separately would be redundant work on an
        # already-known-bad number.
        if len(set(qtys)) > 1 and not has_negative_stock:
            mismatch = {
                "sku": sku,
                "type": "quantity_mismatch",
                "values": {e["source"]: e["qty"] for e in entries},
            }

            # Record which systems were silent for this SKU, so the decision
            # stage can tell "they genuinely disagree" apart from "the system
            # that would have settled it was unreadable". Only attached when
            # there is something to report, so an ordinary mismatch keeps the
            # exact shape — and therefore the exact ledger fingerprint — it had
            # before this was added.
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
