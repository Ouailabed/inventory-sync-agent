"""Tests for a warehouse service that isn't running at all.

test_data_errors.py covers a warehouse that answers with unusable data. This
one covers a warehouse that doesn't answer, so the connection is refused.
"""

import os

import pytest

from warehouse_client import WarehouseClient, WAREHOUSE_CLIENTS
import detect_conflicts

STATE_FILES = [
    "ledger.json",
    "agent.lock",
    "warehouses/warehouse_a_data.json",
    "warehouses/warehouse_b_data.json",
    "warehouses/warehouse_c_data.json",
]

# nothing is listening on this port
DEAD_URL = "http://127.0.0.1:9999"


def cleanup():
    for name in STATE_FILES:
        if os.path.exists(name):
            os.remove(name)


@pytest.fixture
def warehouse_c_down():
    """Point the client for C at a port where nothing is listening."""
    build_defaults()
    original = WAREHOUSE_CLIENTS["C"]
    WAREHOUSE_CLIENTS["C"] = WarehouseClient("C", DEAD_URL)
    yield
    WAREHOUSE_CLIENTS["C"] = original
    cleanup()


def build_defaults():
    cleanup()
    for client in WAREHOUSE_CLIENTS.values():
        client.list_stock()


def conflicts_now():
    combined, data_errors = detect_conflicts.get_combined_stock()
    return detect_conflicts.detect_conflicts(combined, data_errors)


def test_unreachable_service_does_not_crash_the_run(warehouse_c_down):
    from executor import run_agent
    result = run_agent()
    assert result["refused"] is not True


def test_unreachable_service_is_reported_as_a_data_error(warehouse_c_down):
    conflicts = conflicts_now()

    source_errors = [
        c for c in conflicts
        if c["type"] == "data_error" and c["scope"] == "source"
    ]
    assert len(source_errors) == 1
    assert source_errors[0]["source"] == "C"
    assert "not responding" in source_errors[0]["detail"]


def test_unreachable_service_never_produces_a_false_missing_sku(warehouse_c_down):
    """A warehouse that is down must not be treated as an empty one."""
    conflicts = conflicts_now()

    for c in conflicts:
        if c["type"] == "missing_sku":
            assert "C" not in c["missing_from"], (
                f"claimed {c['sku']} is missing from C, but C was never reachable"
            )


def test_the_other_two_warehouses_are_still_compared(warehouse_c_down):
    conflicts = conflicts_now()

    mismatches = [c for c in conflicts if c["type"] == "quantity_mismatch"]
    assert any(c["sku"] == "SKU-001" for c in mismatches), (
        "A and B disagree about SKU-001 and that should still be noticed"
    )


def test_write_failure_is_not_recorded_as_handled():
    """A failed correction must stay out of the ledger so it gets retried."""
    build_defaults()
    try:
        import executor

        original = WAREHOUSE_CLIENTS["B"]

        # reads work, writes fail
        class FailsOnWrite(WarehouseClient):
            def set_qty(self, sku, new_qty):
                raise Exception("warehouse B went away mid-correction")

        WAREHOUSE_CLIENTS["B"] = FailsOnWrite("B", original.base_url)
        try:
            result = executor.run_agent()
        finally:
            WAREHOUSE_CLIENTS["B"] = original

        from ledger import load_ledger
        ledger = load_ledger()

        assert result["failed_actions"] == 1
        assert not any(
            "quantity_mismatch" in fingerprint and "SKU-001" in fingerprint
            for fingerprint in ledger
        ), "a correction that never landed was recorded as handled"
    finally:
        cleanup()
