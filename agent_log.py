"""Structured logging: one JSON object per line, one line per event.

The log used to be free text — pleasant to read, useless to query. Answering
"how many corrections failed this week" or "which SKU gets flagged most" meant
regexing prose that was never designed to be parsed. Worse, the end-of-run
report was written as a single entry spanning twelve physical lines, so even
line-by-line reading produced nonsense.

Each event is now one JSON object on one line, which any log pipeline can read
directly. The human sentence is kept in a `message` field rather than thrown
away, so the file stays greppable and stays readable over someone's shoulder.
The structure is added, not swapped in.

Living in its own module rather than inside ledger.py, which had no business
owning the logger.
"""

import json
import os
from datetime import datetime, timezone

LOG_FILE = "sync_log.txt"


def log_event(event, message=None, sku=None, action=None, **details):
    """Append one event to the log as a single JSON line.

    Empty fields are left out rather than written as null, so each line
    describes what actually happened instead of carrying a fixed schema padded
    with blanks. Anything reading these handles absent keys routinely.
    """
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    if message is not None:
        record["message"] = message
    if sku is not None:
        record["sku"] = sku
    if action is not None:
        record["action"] = action
    if details:
        record["details"] = details

    # Never indent: JSON-lines is only parseable while each record occupies
    # exactly one line. json.dumps escapes any newline inside a value, so a
    # multi-line message can no longer break the file the way it used to.
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def read_events(path=LOG_FILE):
    """Read the log back as a list of dicts.

    The thing the old format couldn't do. Tests assert on events rather than
    hunting for substrings, and it's genuinely useful by hand for questions
    like "show me every failed correction".
    """
    if not os.path.exists(path):
        return []

    events = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
