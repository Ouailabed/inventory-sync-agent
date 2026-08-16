"""Tests that two agents running at the same instant can't both act.

The sequential idempotency proof (run it twice, second run does nothing) has a
gap underneath it: it only holds because the first run finished writing the
ledger before the second run read it. Two processes overlapping in time both
read "not handled yet" and both act.

Reproducing that reliably needs care — see run_two_agents_at_once().
"""

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
    """Start two agent processes at the same wall-clock instant.

    Launching them back to back is not enough. Starting a Python interpreter
    takes longer than the agent's critical section, so the second process would
    normally begin after the first had already finished — and the race would
    quietly fail to reproduce. Instead both children import everything first,
    then spin until a shared start time. The overlap becomes reliable rather
    than a matter of luck.
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
        "no process refused — they both ran:\n\n" + "\n---\n".join(outputs)
    )


def test_no_duplicate_alerts_from_simultaneous_runs():
    """The brief calls out duplicate alerts specifically, so assert on them."""
    cleanup()
    try:
        outputs = run_two_agents_at_once()
    finally:
        cleanup()

    assert count_across(outputs, "RECOUNT TRIGGERED: SKU-002") == 1
    assert count_across(outputs, "FLAGGED: SKU-003") == 1


def test_lock_is_released_so_the_next_run_can_start():
    """A lock that outlives its run would wedge the agent permanently."""
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
    """try/finally, not just a happy-path cleanup."""
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
            "lock survived a crash — every later run would be blocked"
        )
    finally:
        cleanup()


if __name__ == "__main__":
    # Child process used by run_two_agents_at_once().
    # Import first so that only the sync itself lands in the shared window.
    sys.path.insert(0, HERE)
    from executor import run_agent

    start_at = float(sys.argv[1])
    while time.time() < start_at:
        pass

    run_agent()
