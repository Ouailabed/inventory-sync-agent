"""The record of which conflicts have already been dealt with.

This is what makes reruns safe. Every conflict is fingerprinted by its full
content — SKU, type, and the exact values involved — so "already handled" means
"this precise situation was handled", not "we've seen this SKU before". Change
any of the values and it's a new fingerprint, which is what lets the agent tell
a genuinely new conflict apart from one it already fixed.

Logging used to live in here too. It doesn't any more — see agent_log.py.
"""

import json
import os

LEDGER_FILE = "ledger.json"


def load_ledger():
    if not os.path.exists(LEDGER_FILE):
        return {}
    with open(LEDGER_FILE, "r") as f:
        return json.load(f)


def save_ledger(ledger):
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=2)


def make_fingerprint(conflict):
    # sort_keys so two identical conflicts can't fingerprint differently purely
    # because their dict keys happened to be built in a different order.
    return json.dumps(conflict, sort_keys=True)


def already_handled(ledger, fingerprint):
    return fingerprint in ledger


def mark_handled(ledger, fingerprint, decision):
    ledger[fingerprint] = decision
