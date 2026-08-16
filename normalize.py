# What each warehouse calls its SKU and quantity fields.
FIELD_NAMES = {
    "A": {"sku": "sku_id", "qty": "qty"},
    "B": {"sku": "product_code", "qty": "quantity"},
    "C": {"sku": "item", "qty": "stock_level"},
}


def make_data_error(source, sku, detail, raw, scope="record"):
    """Build a data_error conflict. Same shape as the other conflict types."""
    return {
        "sku": sku,
        "type": "data_error",
        "source": source,
        "scope": scope,
        "detail": detail,
        "raw": repr(raw),
    }


def safe_normalize(record, source):
    """Check one raw record and convert it to {sku, qty}.

    Returns (normalized, None) if the record is usable, or (None, data_error)
    if it isn't. Does not raise.
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
    # bool is a subclass of int, so check for it separately
    if isinstance(qty, bool) or not isinstance(qty, (int, float)):
        detail = f"'{fields['qty']}' is not a number: {qty!r}"
        return None, make_data_error(source, sku, detail, record)

    return {"sku": sku, "qty": qty}, None


if __name__ == "__main__":
    good = {"item": "SKU-001", "stock_level": 50}
    print("good record :", safe_normalize(good, "C"))

    for bad in [
        {"item": "SKU-001"},                          # missing quantity
        {"item": "SKU-001", "stock_level": "fifty"},   # not a number
        {"item": "SKU-001", "stock_level": True},      # bool
        {"stock_level": 50},                           # missing sku
        "not-a-record",                                # not a dict
    ]:
        print("bad record  :", safe_normalize(bad, "C")[1]["detail"])
