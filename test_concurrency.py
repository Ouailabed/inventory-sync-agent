"""Tests that two agents started at the same moment can't both act."""

import os
import sys
import time
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

STATE_FILES = [
    "ledger.json",
    "sync_log.txt",
    "agent.lock",
    "warehouses/warehouse_a_data.json",
    "warehouses/warehouse_b_data.json",
    "warehouses/warehouse_c_data.json",
]


def cleanup():
    for name in STATE_FILES:
        path = os.path.join(HERE, name)
        if os.path.exists(path):
            os.remove(path)


def run_two_agents_at_once(delay=2.0):
    """Start two agent processes at the same moment.

    Both children import everything first, then wait for a shared start time.
    Starting them back to back doesn't work - Python startup takes longer than
    the sync itself, so they wouldn't overlap.
    """
    start_at = time.time() + delay
    procs = [
        subprocess.Popen(
            [sys.executable, __file__, str(start_at)],
            cwd=HERE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for _ in range(2)
    ]
    return [p.communicate()[0] for p in procs]


def count_across(outputs, needle):
    return sum(out.count(needle) for out in outputs)


def test_only_one_of_two_simultaneous_runs_acts():
    cleanup()
    try:
        outputs = run_two_agents_at_once()
    finally:
        cleanup()

    # the correction must be applied exactly once, not once per process
    assert count_across(outputs, "CORRECTED: set SKU-001") == 1, (
        "the same fix was applied by both processes:\n\n" + "\n---\n".join(outputs)
    )
    # and exactly one process must have declined to run
    assert count_across(outputs, "REFUSED TO RUN") == 1, (
        "no process refused, they both ran:\n\n" + "\n---\n".join(outputs)
    )


def test_no_duplicate_alerts_from_simultaneous_runs():
    cleanup()
    try:
        outputs = run_two_agents_at_once()
    finally:
        cleanup()

    assert count_across(outputs, "RECOUNT TRIGGERED: SKU-002") == 1
    assert count_across(outputs, "FLAGGED: SKU-003") == 1


def test_lock_is_released_so_the_next_run_can_start():
    cleanup()
    try:
        from executor import run_agent
        run_agent()
        assert not os.path.exists(os.path.join(HERE, "agent.lock"))

        second = run_agent()
        assert second.get("refused") is not True
    finally:
        cleanup()


def test_lock_is_released_even_when_the_run_crashes():
    cleanup()
    try:
        import executor
        from lock import LOCK_FILE

        def explode(*args, **kwargs):
            raise RuntimeError("warehouse exploded mid-sync")

        original = executor.get_combined_stock
        executor.get_combined_stock = explode
        try:
            executor.run_agent()
        except RuntimeError:
            pass
        finally:
            executor.get_combined_stock = original

        assert not os.path.exists(os.path.join(HERE, LOCK_FILE)), (
            "lock survived a crash, so every later run would be blocked"
        )
    finally:
        cleanup()


if __name__ == "__main__":
    # child process used by run_two_agents_at_once()
    sys.path.insert(0, HERE)
    from executor import run_agent

    start_at = float(sys.argv[1])
    while time.time() < start_at:
        pass

    run_agent()
