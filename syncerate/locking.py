"""Per-config, kernel-backed advisory lock for a single Syncerate run.

The persistent lock inode is deliberately NOT unlinked on release: unlinking a
flocked file can allow two different inodes to be locked for the same config.
"""

import errno
import fcntl
import os
from pathlib import Path
import socket
import stat
from datetime import datetime, timezone

from .errors import EXIT_BACKUP_LOCKED, EXIT_LOCK_ERROR, SyncerateError


class BackupLock:
    """Own an open, exclusively flocked file until release or process exit."""

    def __init__(self, path: Path, fd: int) -> None:
        self.path = path
        self._fd = fd

    @classmethod
    def acquire(cls, config_path: str) -> "BackupLock":
        """Lock the canonical TOML pathname without blocking on another run.

        Relative, absolute, and symlink paths to the same TOML share a lock;
        separate TOML paths (even the same basename in different directories)
        remain independent. Failure to establish locking is fatal, not a bypass.
        """
        canonical = Path(config_path).resolve(strict=False)
        lock_path = canonical.with_name(canonical.name + ".lock")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        try:
            fd = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            raise SyncerateError(
                f"Cannot open the backup lock file {lock_path}: {exc}. "
                "The TOML directory must be writable; refusing to run unlocked.",
                EXIT_LOCK_ERROR,
                kind="lock_error",
            ) from exc

        try:
            details = os.fstat(fd)
            if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
                raise OSError("Lock file must be a regular file with exactly one hard link")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
                    raise SyncerateError(
                        f"Backup already running for TOML configuration {canonical}. "
                        f"Lock file: {lock_path}. Skipping this duplicate run.",
                        EXIT_BACKUP_LOCKED,
                        kind="locked",
                    ) from exc
                raise

            # Refuse to overwrite an unrelated existing file by accident.
            os.lseek(fd, 0, os.SEEK_SET)
            previous = os.read(fd, 128)
            if previous and not previous.startswith(b"Syncerate backup lock\n"):
                raise OSError("Existing lock pathname contains an unrelated file")

            metadata = (
                "Syncerate backup lock\n"
                f"config={canonical}\n"
                f"pid={os.getpid()}\n"
                f"host={socket.gethostname()}\n"
                f"started_utc={datetime.now(timezone.utc).isoformat()}\n"
            ).encode("utf-8")
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            written = os.write(fd, metadata)
            if written != len(metadata):
                raise OSError("Could not write complete lock ownership metadata")
            return cls(lock_path, fd)
        except SyncerateError:
            os.close(fd)
            raise
        except OSError as exc:
            os.close(fd)
            raise SyncerateError(
                f"Cannot safely establish backup lock {lock_path}: {exc}. "
                "Refusing to run unlocked.",
                EXIT_LOCK_ERROR,
                kind="lock_error",
            ) from exc

    def release(self) -> None:
        """Close the owner FD, allowing the OS to release flock atomically.

        The inode stays on disk for safe reuse; never unlink it during a run.
        """
        if self._fd is not None:
            fd, self._fd = self._fd, None
            os.close(fd)
