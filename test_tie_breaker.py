"""Tests for what the agent does when the systems can't outvote each other.

decide_action() is a pure function of one conflict, so these call it directly
with hand-built conflicts instead of staging warehouse files.
"""

from decide import decide_action


def mismatch(values, unavailable=None):
    conflict = {"sku": "SKU-001", "type": "quantity_mismatch", "values": values}
    if unavailable:
        conflict["unavailable_sources"] = unavailable
    return conflict


def test_clear_majority_still_corrects_the_outlier():
    decision = decide_action(mismatch({"A": 50, "B": 45, "C": 50}))
    assert decision["action"] == "correct_outlier"
    assert decision["correct_qty"] == 50
    assert decision["fix_sources"] == ["B"]


def test_three_way_split_triggers_a_recount():
    decision = decide_action(mismatch({"A": 50, "B": 45, "C": 30}))
    assert decision["action"] == "trigger_recount"
    assert "no majority" in decision["reason"]


def test_two_way_split_triggers_a_recount():
    decision = decide_action(mismatch({"A": 50, "B": 45}))
    assert decision["action"] == "trigger_recount"


def test_even_split_never_picks_an_arbitrary_winner():
    """With a 4th warehouse a 2-2 split must not 'correct' either side."""
    decision = decide_action(mismatch({"A": 50, "B": 45, "C": 50, "D": 45}))
    assert decision["action"] != "correct_outlier"
    assert decision["action"] == "trigger_recount"


def test_majority_still_wins_with_four_sources():
    """Guard against over-correcting: 3-1 is still a real majority."""
    decision = decide_action(mismatch({"A": 50, "B": 45, "C": 50, "D": 50}))
    assert decision["action"] == "correct_outlier"
    assert decision["correct_qty"] == 50
    assert decision["fix_sources"] == ["B"]


def test_unreadable_source_is_flagged_not_recounted():
    """A recount costs a human walking the floor. Don't spend that on a bug."""
    decision = decide_action(mismatch({"A": 50, "B": 45}, unavailable=["C"]))
    assert decision["action"] == "flag_for_review"
    assert "C" in decision["reason"]


def test_unreadable_source_is_ignored_when_a_majority_exists_anyway():
    """If the readable systems already agree, a missing third doesn't matter."""
    decision = decide_action(mismatch({"A": 50, "B": 50}, unavailable=["C"]))
    assert decision["action"] == "correct_outlier"
