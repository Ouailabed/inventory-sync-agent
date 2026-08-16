"""Running the agent twice should not act twice."""

import os

from warehouse_client import WAREHOUSE_CLIENTS

STATE_FILES = [
    "ledger.json",
    "agent.lock",
    "warehouses/warehouse_a_data.json",
    "warehouses/warehouse_b_data.json",
    "warehouses/warehouse_c_data.json",
]


def cleanup():
    for name in STATE_FILES:
        if os.path.exists(name):
            os.remove(name)


def find_record(source, sku):
    for record in WAREHOUSE_CLIENTS[source].list_stock():
        if sku in record.values():
            return record
    return None


def test_second_run_makes_no_new_actions():
    cleanup()
    try:
        from executor import run_agent
        from ledger import load_ledger

        run_agent()
        first_run_size = len(load_ledger())

        run_agent()
        second_run_size = len(load_ledger())
    finally:
        cleanup()

    assert first_run_size > 0
    assert second_run_size == first_run_size


def test_correction_persists_to_warehouse_b():
    """Read the value back over HTTP to check the write really happened."""
    cleanup()
    try:
        from executor import run_agent

        run_agent()
        record = find_record("B", "SKU-001")
    finally:
        cleanup()

    assert record is not None
    assert record["quantity"] == 50
