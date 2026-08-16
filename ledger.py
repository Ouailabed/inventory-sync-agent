"""Keeps track of which conflicts have already been handled.

Each conflict is fingerprinted from its full content, so a conflict with
different values counts as a new one.
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
    # sort_keys keeps the fingerprint stable whatever order the keys were added
    return json.dumps(conflict, sort_keys=True)


def already_handled(ledger, fingerprint):
    return fingerprint in ledger


def mark_handled(ledger, fingerprint, decision):
    ledger[fingerprint] = decision
