"""Tests for the malformed / corrupted data handling.

The point of every test here is the same: the agent must survive bad input from
one warehouse and still do useful work with the other two.
"""

import os
import json

from warehouse_client import WAREHOUSE_CLIENTS

DATA_FILES = {
    "A": "warehouses/warehouse_a_data.json",
    "B": "warehouses/warehouse_b_data.json",
    "C": "warehouses/warehouse_c_data.json",
}

STATE_FILES = ["ledger.json", "agent.lock"] + list(DATA_FILES.values())


def cleanup():
    for f in STATE_FILES:
        if os.path.exists(f):
            os.remove(f)


def build_default_files():
    """Ask each service for its stock, which makes it write its default file."""
    cleanup()
    for client in WAREHOUSE_CLIENTS.values():
        client.list_stock()


def write_raw(source, text):
    with open(DATA_FILES[source], "w") as f:
        f.write(text)


def conflicts_now():
    from detect_conflicts import get_combined_stock, detect_conflicts
    combined, data_errors = get_combined_stock()
    return detect_conflicts(combined, data_errors)


def test_corrupted_json_file_does_not_crash_the_run():
    """A warehouse whose file is unparseable costs us that warehouse, not the run."""
    build_default_files()
    write_raw("C", '{"SKU-001": {"item": "SKU-001", "stock_lev')
    try:
        conflicts = conflicts_now()
    finally:
        cleanup()

    source_errors = [c for c in conflicts if c["type"] == "data_error" and c["scope"] == "source"]
    assert len(source_errors) == 1
    assert source_errors[0]["source"] == "C"

    # and the other two warehouses were still compared against each other
    assert any(c["type"] == "quantity_mismatch" for c in conflicts)


def test_unreadable_source_does_not_invent_missing_skus():
    """We couldn't ask warehouse C, so we must not claim C is missing anything."""
    build_default_files()
    write_raw("C", "this is not json at all")
    try:
        conflicts = conflicts_now()
    finally:
        cleanup()

    for c in conflicts:
        if c["type"] == "missing_sku":
            assert "C" not in c["missing_from"], (
                f"claimed {c['sku']} is missing from C, but C never answered"
            )


def test_broken_record_is_not_also_reported_as_missing():
    """C has SKU-001, it's just unreadable. "Missing from C" would be a lie."""
    build_default_files()
    write_raw("C", json.dumps({
        "SKU-001": {"item": "SKU-001"},                     # unusable
        "SKU-002": {"item": "SKU-002", "stock_level": -3},  # fine
    }))
    try:
        conflicts = conflicts_now()
    finally:
        cleanup()

    missing = [c for c in conflicts if c["type"] == "missing_sku" and c["sku"] == "SKU-001"]
    assert missing == [], f"SKU-001 wrongly reported missing: {missing}"

    # it is still reported — as the data problem it actually is
    assert any(
        c["type"] == "data_error" and c["sku"] == "SKU-001" for c in conflicts
    )


def test_one_bad_record_does_not_hide_the_good_ones():
    """A single unusable row is isolated; its neighbours are still processed."""
    build_default_files()
    write_raw("A", json.dumps({
        "SKU-001": {"sku_id": "SKU-001", "qty": "fifty"},   # not a number
        "SKU-002": {"sku_id": "SKU-002", "qty": 12},        # perfectly fine
    }))
    try:
        from detect_conflicts import get_combined_stock
        combined, data_errors = get_combined_stock()
    finally:
        cleanup()

    a_records = [r for r in combined if r["source"] == "A"]
    assert [r["sku"] for r in a_records] == ["SKU-002"]

    assert len(data_errors) == 1
    assert data_errors[0]["sku"] == "SKU-001"
    assert data_errors[0]["scope"] == "record"


def test_missing_field_is_reported_by_name():
    """The flag should tell a human which field to go and look at."""
    build_default_files()
    write_raw("C", json.dumps({"SKU-001": {"item": "SKU-001"}}))
    try:
        from detect_conflicts import get_combined_stock
        _, data_errors = get_combined_stock()
    finally:
        cleanup()

    assert len(data_errors) == 1
    assert "stock_level" in data_errors[0]["detail"]


def test_data_errors_are_idempotent_too():
    """Bad data must not produce a fresh duplicate alert on every single run."""
    build_default_files()
    write_raw("C", json.dumps({"SKU-001": {"item": "SKU-001", "stock_level": None}}))
    try:
        from executor import run_agent
        first = run_agent()
        second = run_agent()
    finally:
        cleanup()

    assert first["new_actions"] > 0
    assert second["new_actions"] == 0
