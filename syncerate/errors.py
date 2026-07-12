"""Exit codes and the application exception used across Syncerate."""

from typing import Optional

EXIT_OK = 0
EXIT_LIST_ERROR = 1
EXIT_SCRIPT_ERROR = 2
EXIT_WARNING = 4
EXIT_PASSWORD_DENIED = 5
EXIT_CONNECTION_TIMEOUT = 6
EXIT_CONNECTION_REFUSED = 7
EXIT_DATASET_MISSING = 8
EXIT_REPEATED_PATTERN = 9
EXIT_MQTT_ERROR = 10
EXIT_SYSTEM_ACTION_ERROR = 11


class SyncerateError(Exception):
    """Known application failure carrying the intended process exit code."""

    def __init__(
        self,
        message: str,
        exit_code: int,
        *,
        kind: str = "script",
        child_before: str = "",
        child_warning: str = "",
        syncoid_before: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = int(exit_code)
        self.kind = kind
        self.child_before = child_before
        self.child_warning = child_warning
        self.syncoid_before = syncoid_before
