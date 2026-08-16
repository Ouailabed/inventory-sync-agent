def decide_action(conflict):
    """Return the action to take for one conflict."""
    if conflict["type"] == "quantity_mismatch":
        values = conflict["values"]

        # group the systems by the number each one reported
        sources_by_qty = {}
        for source, qty in values.items():
            sources_by_qty.setdefault(qty, []).append(source)

        best_qty = max(sources_by_qty, key=lambda q: len(sources_by_qty[q]))
        agreeing = sources_by_qty[best_qty]
        runners_up = [q for q in sources_by_qty if len(sources_by_qty[q]) == len(agreeing)]

        # A majority needs 2+ systems on the same number, and no tie for first.
        # The tie check matters once there are 4+ warehouses (a 2-2 split).
        if len(agreeing) >= 2 and len(runners_up) == 1:
            outlier_sources = [s for s in values if s not in agreeing]
            return {
                "sku": conflict["sku"],
                "action": "correct_outlier",
                "correct_qty": best_qty,
                "fix_sources": outlier_sources,
            }

        # No majority.
        reported = ", ".join(f"{s}={q}" for s, q in sorted(values.items()))

        # If a source we couldn't read might have broken the tie, that's a data
        # problem, not a stock problem. Don't order a recount for it.
        unreadable = conflict.get("unavailable_sources")
        if unreadable:
            return {
                "sku": conflict["sku"],
                "action": "flag_for_review",
                "reason": (
                    f"tie among {reported} and {unreadable} could not be read "
                    f"- fix the data source, then re-run before ordering a recount"
                ),
            }

        # The systems really disagree, so only a physical count settles it.
        return {
            "sku": conflict["sku"],
            "action": "trigger_recount",
            "reason": f"no majority among {reported} - physical count needed",
        }

    elif conflict["type"] == "missing_sku":
        return {
            "sku": conflict["sku"],
            "action": "flag_for_review",
            "reason": f"missing from {conflict['missing_from']}",
        }

    elif conflict["type"] == "data_error":
        # nothing safe to calculate from broken data, so a human looks at it
        where = f"warehouse {conflict['source']}"
        return {
            "sku": conflict["sku"],
            "action": "flag_for_review",
            "reason": f"bad data in {where}: {conflict['detail']}",
        }

    elif conflict["type"] == "negative_stock":
        return {
            "sku": conflict["sku"],
            "action": "trigger_recount",
            "reason": f"negative stock in {conflict['source']}",
        }

    return {
        "sku": conflict["sku"],
        "action": "flag_for_review",
        "reason": "unknown conflict type",
    }


if __name__ == "__main__":
    from detect_conflicts import get_combined_stock, detect_conflicts

    combined, data_errors = get_combined_stock()
    conflicts = detect_conflicts(combined, data_errors)

    for c in conflicts:
        decision = decide_action(c)
        print(decision)