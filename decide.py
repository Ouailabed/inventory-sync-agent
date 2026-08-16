def decide_action(conflict):
    if conflict["type"] == "quantity_mismatch":
        values = conflict["values"]

        # group the systems by the number each one reported
        sources_by_qty = {}
        for source, qty in values.items():
            sources_by_qty.setdefault(qty, []).append(source)

        best_qty = max(sources_by_qty, key=lambda q: len(sources_by_qty[q]))
        agreeing = sources_by_qty[best_qty]
        runners_up = [q for q in sources_by_qty if len(sources_by_qty[q]) == len(agreeing)]

        # A usable majority needs two things: at least two independent systems
        # reporting the same number, and no other number matching that count.
        # The second half looks redundant with only three warehouses (the most
        # even split possible is 2-1), but add a fourth and a 2-2 split would
        # otherwise pick a "winner" arbitrarily and overwrite two systems that
        # were just as credible as the two it sided with.
        if len(agreeing) >= 2 and len(runners_up) == 1:
            outlier_sources = [s for s in values if s not in agreeing]
            return {
                "sku": conflict["sku"],
                "action": "correct_outlier",
                "correct_qty": best_qty,
                "fix_sources": outlier_sources,
            }

        # No majority. Every system is reporting something different, so there
        # is no number here worth trusting and no cleverer way to compute one.
        reported = ", ".join(f"{s}={q}" for s, q in sorted(values.items()))

        # ...but first, check *why* the vote failed. If a system that could have
        # broken the tie simply couldn't be read, that is a software problem,
        # and a recount means sending a person to physically walk the floor.
        # Fix the feed and re-run before spending that.
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

        # Nothing was unreadable — the systems genuinely disagree. A recount is
        # the only thing that produces a number worth writing. Parking this in a
        # review queue would just hand a human the same dead end the agent hit.
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
        # Always a human's call. Every other action this agent takes is based on
        # trusting the numbers it read; here the numbers are exactly what's
        # broken, so there is nothing safe to compute from.
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