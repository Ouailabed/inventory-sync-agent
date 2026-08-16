"""Event log. One JSON object per line."""

import json
import os
from datetime import datetime, timezone

LOG_FILE = "sync_log.txt"


def log_event(event, message=None, sku=None, action=None, **details):
    """Append one event to the log. Fields left as None are omitted."""
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

    # no indent - each record has to stay on one line
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def read_events(path=LOG_FILE):
    """Read the log back as a list of dicts. Returns [] if the file is missing."""
    if not os.path.exists(path):
        return []

    events = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
