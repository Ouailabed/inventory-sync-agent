import argparse
import time

# No sys.path juggling any more: the warehouses aren't importable modules that
# happen to live in a subdirectory, they're services reached over HTTP.
from detect_conflicts import get_combined_stock, detect_conflicts
from warehouse_client import WAREHOUSE_CLIENTS
from decide import decide_action
from ledger import load_ledger, save_ledger, make_fingerprint, already_handled, mark_handled
from lock import acquire_lock, release_lock, describe_holder, read_lock
from agent_log import log_event

def apply_action(decision, dry_run=False):
    """Carry out one decision. Returns True only if it fully succeeded.

    The return value is the point. Now that corrections travel over the network,
    a warehouse can be readable when we poll it and gone by the time we write to
    it. If a failed correction were still written into the ledger, the agent
    would consider it handled and never try again — the ledger would be claiming
    a fix that never landed, which is worse than no ledger at all.
    """
    action = decision["action"]

    sku = decision["sku"]

    if action == "correct_outlier":
        succeeded = True
        for source in decision["fix_sources"]:
            if dry_run:
                msg = f"[DRY RUN] would set {sku} to {decision['correct_qty']} in warehouse {source}"
                event = "action_simulated"
                extra = {}
            else:
                try:
                    WAREHOUSE_CLIENTS[source].set_qty(sku, decision["correct_qty"])
                    msg = f"CORRECTED: set {sku} to {decision['correct_qty']} in warehouse {source}"
                    event = "action_applied"
                    extra = {}
                except Exception as e:
                    # Safe to retry next run: the correction is an absolute set,
                    # not an adjustment, so applying it twice lands on the same
                    # number. A "subtract 5" style fix would need more care.
                    msg = f"CORRECTION FAILED: {sku} in warehouse {source} - {e} - will retry next run"
                    event = "action_failed"
                    extra = {"error": str(e)}
                    succeeded = False

            print(msg)
            log_event(event, message=msg, sku=sku, action=action,
                      warehouse=source, new_qty=decision["correct_qty"], **extra)
        return succeeded

    elif action == "flag_for_review":
        prefix = "[DRY RUN] would flag" if dry_run else "FLAGGED"
        msg = f"{prefix}: {sku} - {decision['reason']}"
        print(msg)
        log_event("action_simulated" if dry_run else "action_applied",
                  message=msg, sku=sku, action=action, reason=decision["reason"])
        return True

    elif action == "trigger_recount":
        prefix = "[DRY RUN] would trigger recount" if dry_run else "RECOUNT TRIGGERED"
        msg = f"{prefix}: {sku} - {decision['reason']}"
        print(msg)
        log_event("action_simulated" if dry_run else "action_applied",
                  message=msg, sku=sku, action=action, reason=decision["reason"])
        return True

    return True


def run_agent(dry_run=False):
    """Run one sync, unless another one is already in flight.

    The ledger alone makes *sequential* reruns safe: the second run reads what
    the first one wrote and skips it. That breaks down when two runs overlap in
    time — both read the ledger before either has written to it, both see
    "not handled", and both act. Verified in test_concurrency.py: without this
    guard, two simultaneous runs apply every correction twice and send every
    alert twice.

    The lock is taken for dry runs too. A dry run writes nothing, so it can't
    double-apply anything, but it would still be reading a ledger and warehouse
    files that another process is part-way through rewriting, and reporting
    that half-written state as if it were the truth.
    """
    if not acquire_lock():
        msg = f"REFUSED TO RUN: {describe_holder()}"
        print(msg)
        log_event("run_refused", message=msg, holder=read_lock())
        return {
            "new_actions": 0,
            "skipped_actions": 0,
            "failed_actions": 0,
            "summary": {},
            "skus_touched": [],
            "refused": True,
        }

    # finally, not just a line at the end: a crash mid-sync must still release
    # the lock, or every future run is blocked by a process that no longer runs.
    try:
        return _perform_sync(dry_run=dry_run)
    finally:
        release_lock()


def _perform_sync(dry_run=False):
    ledger = load_ledger()
    combined, data_errors = get_combined_stock()
    conflicts = detect_conflicts(combined, data_errors)

    new_actions = 0
    skipped_actions = 0
    failed_actions = 0
    summary = {}
    skus_touched = set()

    log_event("run_started", message="run started", dry_run=dry_run,
              conflicts_scanned=len(conflicts))

    for conflict in conflicts:
        fingerprint = make_fingerprint(conflict)

        if already_handled(ledger, fingerprint):
            msg = f"SKIPPED (already handled): {conflict['sku']} - {conflict['type']}"
            print(msg)
            log_event("conflict_skipped", message=msg, sku=conflict["sku"],
                      conflict_type=conflict["type"])
            skipped_actions += 1
            continue

        decision = decide_action(conflict)
        applied = apply_action(decision, dry_run=dry_run)

        if not applied:
            # Left out of the ledger on purpose, so the next run picks it up.
            failed_actions += 1
            continue

        if not dry_run:
            mark_handled(ledger, fingerprint, decision)

        new_actions += 1
        skus_touched.add(conflict["sku"])
        action_type = decision["action"]
        summary[action_type] = summary.get(action_type, 0) + 1

    if not dry_run:
        save_ledger(ledger)

    report_lines = []
    report_lines.append("")
    report_lines.append("========== SYNC REPORT ==========")
    report_lines.append(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    report_lines.append(f"Total conflicts scanned: {len(conflicts)}")
    report_lines.append(f"New actions taken: {new_actions}")
    report_lines.append(f"Already-handled (skipped): {skipped_actions}")
    report_lines.append(f"Failed (not ledgered, will retry): {failed_actions}")
    report_lines.append(f"Distinct SKUs affected this run: {len(skus_touched)}")
    if summary:
        report_lines.append("Breakdown by action type:")
        for action_type, count in summary.items():
            report_lines.append(f"  - {action_type}: {count}")
    else:
        report_lines.append("Breakdown by action type: none (nothing new to act on)")
    report_lines.append("==================================")

    # The pretty block goes to the console for a human watching the run. The log
    # gets the same numbers as fields instead — which is the whole point of the
    # change, since "runs where failed > 0" is now a query rather than a regex.
    print("\n".join(report_lines))
    log_event(
        "run_finished",
        message=f"run finished: {new_actions} new, {skipped_actions} skipped, {failed_actions} failed",
        mode="dry_run" if dry_run else "live",
        conflicts_scanned=len(conflicts),
        new_actions=new_actions,
        skipped_actions=skipped_actions,
        failed_actions=failed_actions,
        skus_affected=sorted(skus_touched),
        breakdown=summary,
    )

    return {
        "new_actions": new_actions,
        "skipped_actions": skipped_actions,
        "failed_actions": failed_actions,
        "summary": summary,
        "skus_touched": list(skus_touched),
        # always present, so callers never have to guess whether the key exists
        "refused": False,
    }


def run_scheduled(interval_seconds, dry_run=False, max_runs=None):
    """Run the agent every interval_seconds until stopped with Ctrl-C.

    A plain loop with time.sleep() rather than a scheduling library. At this
    size there is nothing a library would do better, and it's one less
    dependency to install and explain.

    Three things here are deliberate:

    - The sleep is shortened by however long the run took, so the gap between
      runs stays at interval_seconds instead of drifting out by the duration of
      every run. If a run overruns the interval the next starts immediately,
      which catches up rather than building a backlog.

    - A failed run is logged and the loop carries on. An unattended agent that
      dies on its first bad tick is worse than no agent, because nobody finds
      out until someone notices the stock is wrong.

    - There is no concurrency handling here on purpose. Runs inside this loop
      are sequential by construction, and anything running *outside* it — a
      second scheduler, someone triggering a manual sync — is already handled
      by the lock in run_agent(). A tick that gets refused just tries again on
      the next one.
    """
    if interval_seconds <= 0:
        raise ValueError("interval must be greater than zero")

    start_msg = f"=== Scheduler started: every {interval_seconds}s (dry_run={dry_run}) ==="
    print(start_msg + "\nCtrl-C to stop.\n")
    log_event("scheduler_started", message=start_msg,
              interval_seconds=interval_seconds, dry_run=dry_run, max_runs=max_runs)

    runs = 0
    try:
        while True:
            runs += 1
            started_at = time.monotonic()

            header = f"----- scheduled run #{runs} -----"
            print(header)
            log_event("scheduler_run_starting", message=header, run=runs)

            try:
                run_agent(dry_run=dry_run)
            except Exception as e:
                msg = f"SCHEDULED RUN #{runs} FAILED: {type(e).__name__}: {e} - trying again next tick"
                print(msg)
                log_event("scheduler_run_failed", message=msg, run=runs,
                          error=str(e), error_type=type(e).__name__)

            if max_runs is not None and runs >= max_runs:
                break

            # monotonic, not wall clock: immune to the system clock being
            # adjusted underneath a long-running process.
            elapsed = time.monotonic() - started_at
            time.sleep(max(0, interval_seconds - elapsed))
    except KeyboardInterrupt:
        print()  # so the stop message isn't stuck on the same line as ^C

    stop_msg = f"=== Scheduler stopped after {runs} run(s) ==="
    print(stop_msg)
    log_event("scheduler_stopped", message=stop_msg, runs=runs)
    return runs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inventory sync agent")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without applying changes")
    parser.add_argument("--interval", type=float, metavar="SECONDS",
                        help="Run repeatedly, this many seconds apart, until Ctrl-C")
    parser.add_argument("--max-runs", type=int, metavar="N",
                        help="With --interval, stop after N runs instead of running forever")
    args = parser.parse_args()

    if args.interval:
        run_scheduled(args.interval, dry_run=args.dry_run, max_runs=args.max_runs)
    else:
        run_agent(dry_run=args.dry_run)