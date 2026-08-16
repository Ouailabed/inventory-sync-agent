"""Tests for running the agent on a timer.

The one that matters is test_repeated_runs_only_act_once: scheduling is where
a non-idempotent agent does real damage, because nobody is watching it do so.
"""

import os
import time

import executor
from executor import run_scheduled
from agent_log import read_events

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
        if os.path.exists(name):
            os.remove(name)


def events_of(events, event_type):
    return [e for e in events if e["event"] == event_type]


def actions_on(events, sku, action):
    return [
        e for e in events
        if e["event"] == "action_applied"
        and e.get("sku") == sku
        and e.get("action") == action
    ]


def test_scheduler_runs_the_requested_number_of_times():
    cleanup()
    try:
        runs = run_scheduled(0.1, max_runs=3)
        events = read_events()
    finally:
        cleanup()

    assert runs == 3
    starts = events_of(events, "scheduler_run_starting")
    assert [e["details"]["run"] for e in starts] == [1, 2, 3]


def test_repeated_runs_only_act_once():
    """Idempotency has to survive being run on a timer, not just twice by hand."""
    cleanup()
    try:
        run_scheduled(0.1, max_runs=4)
        events = read_events()
    finally:
        cleanup()

    assert len(actions_on(events, "SKU-001", "correct_outlier")) == 1
    assert len(actions_on(events, "SKU-002", "trigger_recount")) == 1
    assert len(actions_on(events, "SKU-003", "flag_for_review")) == 1


def test_every_scheduled_run_is_logged_like_a_manual_one():
    cleanup()
    try:
        run_scheduled(0.1, max_runs=2)
        events = read_events()
    finally:
        cleanup()

    # the same run markers a manual invocation writes
    assert len(events_of(events, "run_started")) == 2
    assert len(events_of(events, "run_finished")) == 2
    assert len(events_of(events, "scheduler_started")) == 1

    stopped = events_of(events, "scheduler_stopped")
    assert len(stopped) == 1
    assert stopped[0]["details"]["runs"] == 2


def test_a_failing_run_does_not_kill_the_scheduler():
    """One bad tick must not end an unattended agent."""
    cleanup()
    calls = {"n": 0}
    original = executor.run_agent

    def fail_on_the_second_call(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("warehouse fell over")
        return original(*args, **kwargs)

    executor.run_agent = fail_on_the_second_call
    try:
        runs = run_scheduled(0.05, max_runs=3)
        events = read_events()
    finally:
        executor.run_agent = original
        cleanup()

    assert runs == 3
    assert calls["n"] == 3

    failures = events_of(events, "scheduler_run_failed")
    assert len(failures) == 1
    assert failures[0]["details"]["run"] == 2
    assert failures[0]["details"]["error_type"] == "RuntimeError"


def test_ctrl_c_stops_cleanly_and_leaves_no_lock():
    """Ctrl-C mid-run must not strand the lock and wedge every future run.

    Interrupts the genuine run_agent() rather than a stand-in, so the real
    try/finally is what's under test.
    """
    cleanup()
    original = executor.get_combined_stock

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt()

    executor.get_combined_stock = interrupted
    try:
        runs = run_scheduled(0.1, max_runs=5)
        events = read_events()
    finally:
        executor.get_combined_stock = original
        cleanup()

    # stopped on the first tick rather than running all five
    assert runs == 1
    stopped = events_of(events, "scheduler_stopped")
    assert stopped[0]["details"]["runs"] == 1
    assert not os.path.exists("agent.lock"), "Ctrl-C left the lock behind"


def test_interval_is_respected_between_runs():
    cleanup()
    try:
        started = time.monotonic()
        run_scheduled(0.4, max_runs=3)
        elapsed = time.monotonic() - started
    finally:
        cleanup()

    # 3 runs means 2 gaps; loose lower bound, generous upper bound so this
    # doesn't turn into a flaky test on a busy machine
    assert elapsed >= 0.8, f"ran too fast ({elapsed:.2f}s) - interval ignored"
    assert elapsed < 6.0, f"took far too long ({elapsed:.2f}s)"


def test_zero_interval_is_rejected():
    """A zero or negative interval would be a busy loop hammering the services."""
    for bad in (0, -5):
        try:
            run_scheduled(bad, max_runs=1)
            assert False, f"interval {bad} should have been rejected"
        except ValueError:
            pass
