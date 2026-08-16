"""Tests that every line of the log is a complete JSON object."""

import json
import os

from agent_log import LOG_FILE, log_event, read_events

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


def test_every_line_of_a_real_run_is_valid_json():
    cleanup()
    try:
        from executor import run_agent
        run_agent()

        with open(LOG_FILE) as f:
            lines = [line for line in f if line.strip()]

        for number, line in enumerate(lines, 1):
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                raise AssertionError(f"line {number} isn't valid JSON: {e}\n{line!r}")
    finally:
        cleanup()

    assert len(lines) > 1


def test_events_carry_the_fields_needed_to_query_them():
    cleanup()
    try:
        from executor import run_agent
        run_agent()
        events = read_events()
    finally:
        cleanup()

    for event in events:
        assert "timestamp" in event
        assert "event" in event

    corrections = [
        e for e in events
        if e["event"] == "action_applied" and e.get("action") == "correct_outlier"
    ]
    assert len(corrections) == 1
    assert corrections[0]["sku"] == "SKU-001"
    assert corrections[0]["details"]["warehouse"] == "B"
    assert corrections[0]["details"]["new_qty"] == 50


def test_run_summary_is_queryable_instead_of_a_wall_of_text():
    """The end-of-run summary is one object with the counts as fields."""
    cleanup()
    try:
        from executor import run_agent
        run_agent()
        events = read_events()
    finally:
        cleanup()

    finished = [e for e in events if e["event"] == "run_finished"]
    assert len(finished) == 1

    details = finished[0]["details"]
    assert details["mode"] == "live"
    assert details["new_actions"] == 4
    assert details["failed_actions"] == 0
    assert details["breakdown"]["correct_outlier"] == 1


def test_a_multi_line_message_cannot_break_the_format():
    """A newline inside a message must not split the record over two lines."""
    cleanup()
    try:
        log_event("test_event", message="first line\nsecond line\nthird line")

        with open(LOG_FILE) as f:
            lines = [line for line in f if line.strip()]

        assert len(lines) == 1, "a newline in a value split the record across lines"
        assert json.loads(lines[0])["message"] == "first line\nsecond line\nthird line"
    finally:
        cleanup()


def test_empty_fields_are_left_out_rather_than_written_as_null():
    cleanup()
    try:
        log_event("test_event", message="no sku here")
        event = read_events()[0]
    finally:
        cleanup()

    assert "sku" not in event
    assert "action" not in event
    assert "details" not in event


def test_reading_an_absent_log_returns_nothing_rather_than_raising():
    cleanup()
    assert read_events("does_not_exist.txt") == []
