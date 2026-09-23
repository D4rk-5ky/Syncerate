"""Bounded cleanup for process groups owned by this Syncerate invocation."""

import os
import signal
import time


def terminate_process_group(process_group: int, grace_seconds: float = 1.0) -> None:
    """Send TERM, then KILL after a short grace period to an owned POSIX group.

    Callers must supply a group created for their own child, never a discovered
    system-wide process list. Refuse our own group even if a caller is mistaken.
    No ZFS rollback, receive-abort, snapshot deletion, or pool change is done.
    """

    if process_group <= 1 or process_group == os.getpgrp():
        raise ValueError("Refusing to signal an unsafe process group")
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        return
    # A fixed short grace also works when a sandbox forbids killpg(..., 0).
    # Keep this bounded even if a child ignores TERM or leaves a zombie leader.
    time.sleep(grace_seconds)
    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        pass
