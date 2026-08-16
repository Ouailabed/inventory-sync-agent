"""A single-holder lock, so only one sync can be in flight at a time.

The obvious way to write this is:

    if os.path.exists(LOCK_FILE):    # <-- don't
        return False
    open(LOCK_FILE, "w").close()

which has exactly the bug the lock is supposed to fix. Two processes can both
run the check before either has created the file, and both conclude they're
alone. The gap is small, but it's the same kind of gap as the one in the agent
itself, so closing it with a wider version of it would be pointless.

os.open(..., O_CREAT | O_EXCL) instead asks the operating system to create the
file *only if it does not already exist*, as one indivisible step. Exactly one
caller can win that, no matter how the two processes interleave.
"""

import os
import json
from datetime import datetime, timezone

LOCK_FILE = "agent.lock"


def acquire_lock():
    """Try to become the one running sync. True if we got it, False if not."""
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False

    # Record who holds it. This is only ever read by a human working out why a
    # run was refused — the exclusion itself is done by the OS above.
    holder = {
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    with os.fdopen(fd, "w") as f:
        json.dump(holder, f)
    return True


def read_lock():
    """Who currently holds the lock? Returns {} if we can't tell."""
    try:
        with open(LOCK_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # The holder may still have been mid-write when we looked. Not knowing
        # who holds it doesn't change the answer: we still aren't running.
        return {}


def release_lock():
    """Give up the lock. Safe to call even if it's already gone."""
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass


def describe_holder():
    holder = read_lock()
    if not holder:
        return "another sync is already running"
    return (
        f"another sync is already running "
        f"(pid {holder.get('pid', '?')}, started {holder.get('started_at', '?')})"
    )
