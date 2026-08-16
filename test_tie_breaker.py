"""Tests for how quantity mismatches are decided.

decide_action() only needs one conflict dict, so these build them by hand
instead of setting up warehouse data.
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
    """A 2-2 split with 4 warehouses must not correct either side."""
    decision = decide_action(mismatch({"A": 50, "B": 45, "C": 50, "D": 45}))
    assert decision["action"] != "correct_outlier"
    assert decision["action"] == "trigger_recount"


def test_majority_still_wins_with_four_sources():
    """3-1 is still a majority, so it should still be corrected."""
    decision = decide_action(mismatch({"A": 50, "B": 45, "C": 50, "D": 50}))
    assert decision["action"] == "correct_outlier"
    assert decision["correct_qty"] == 50
    assert decision["fix_sources"] == ["B"]


def test_unreadable_source_is_flagged_not_recounted():
    """A tie caused by unreadable data is a data problem, not a stock problem."""
    decision = decide_action(mismatch({"A": 50, "B": 45}, unavailable=["C"]))
    assert decision["action"] == "flag_for_review"
    assert "C" in decision["reason"]


def test_unreadable_source_is_ignored_when_a_majority_exists_anyway():
    """If the readable systems already agree, the missing one doesn't matter."""
    decision = decide_action(mismatch({"A": 50, "B": 50}, unavailable=["C"]))
    assert decision["action"] == "correct_outlier"
