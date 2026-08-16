# Each warehouse invented its own names for the same two pieces of information.
# Keeping that mapping in one table means the validator below can name the exact
# field a bad record is missing, instead of just saying "something was wrong".
FIELD_NAMES = {
    "A": {"sku": "sku_id", "qty": "qty"},
    "B": {"sku": "product_code", "qty": "quantity"},
    "C": {"sku": "item", "qty": "stock_level"},
}


def make_data_error(source, sku, detail, raw, scope="record"):
    """Build a 'this data is unusable' conflict.

    Deliberately shaped like every other conflict (it has a sku and a type) so
    the decide/apply/ledger pipeline can carry it without special-casing.
    """
    return {
        "sku": sku,
        "type": "data_error",
        "source": source,
        "scope": scope,
        "detail": detail,
        "raw": repr(raw),
    }


def safe_normalize(record, source):
    """Validate and normalize one raw record.

    Returns (normalized, None) if the record is usable, or (None, data_error)
    if it isn't. Never raises — a single bad record must not stop the sync.

    Bad values are rejected rather than guessed at. A quantity of "fifty" could
    plausibly be coerced to 50, but this agent writes corrections into live
    inventory, and a wrong guess there is worse than an unresolved flag.
    """
    fields = FIELD_NAMES[source]

    if not isinstance(record, dict):
        return None, make_data_error(source, "UNKNOWN", "record is not an object", record)

    sku = record.get(fields["sku"])
    if not isinstance(sku, str) or not sku.strip():
        detail = f"missing or invalid '{fields['sku']}'"
        return None, make_data_error(source, "UNKNOWN", detail, record)

    if fields["qty"] not in record:
        detail = f"missing '{fields['qty']}'"
        return None, make_data_error(source, sku, detail, record)

    qty = record[fields["qty"]]
    # bool is a subclass of int in Python, so a stray `true` would otherwise
    # sail through this check and silently become a quantity of 1.
    if isinstance(qty, bool) or not isinstance(qty, (int, float)):
        detail = f"'{fields['qty']}' is not a number: {qty!r}"
        return None, make_data_error(source, sku, detail, record)

    return {"sku": sku, "qty": qty}, None


if __name__ == "__main__":
    good = {"item": "SKU-001", "stock_level": 50}
    print("good record :", safe_normalize(good, "C"))

    for bad in [
        {"item": "SKU-001"},                        # missing quantity
        {"item": "SKU-001", "stock_level": "fifty"},  # not a number
        {"item": "SKU-001", "stock_level": True},     # bool sneaking in as 1
        {"stock_level": 50},                          # missing sku
        "not-a-record",                               # not an object at all
    ]:
        print("bad record  :", safe_normalize(bad, "C")[1]["detail"])
