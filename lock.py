"""Lock file so only one sync runs at a time."""

import os
import json
from datetime import datetime, timezone

LOCK_FILE = "agent.lock"


def acquire_lock():
    """Take the lock. Returns True if we got it, False if someone else has it."""
    # O_CREAT | O_EXCL creates the file only if it doesn't exist, in one step.
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False

    holder = {
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    with os.fdopen(fd, "w") as f:
        json.dump(holder, f)
    return True


def read_lock():
    """Return the pid and start time of the lock holder, or {} if unknown."""
    try:
        with open(LOCK_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # gone, or still being written
        return {}


def release_lock():
    """Remove the lock file. Does nothing if it isn't there."""
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass


def describe_holder():
    """Message describing who holds the lock."""
    holder = read_lock()
    if not holder:
        return "another sync is already running"
    return (
        f"another sync is already running "
        f"(pid {holder.get('pid', '?')}, started {holder.get('started_at', '?')})"
    )
