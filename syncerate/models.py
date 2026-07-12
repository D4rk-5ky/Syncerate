"""Dataclasses that carry configuration and per-run state explicitly."""

import configparser
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class AppConfig:
    """Validated application settings loaded from one configuration file."""

    config_path: str
    raw_config: configparser.RawConfigParser
    mail_option: str
    system_option: str
    use_mqtt: bool
    datetime_format: str
    log_destination: Optional[str]
    backup_title: str
    backup_comment: str
    source_list_path: str
    destination_list_path: str
    password_option: str
    syncoid_command: str

    @property
    def mail_enabled(self) -> bool:
        return self.mail_option.strip().upper() != "NO"

    @property
    def system_action_enabled(self) -> bool:
        return self.system_option.strip().upper() != "NO"

    @property
    def logging_enabled(self) -> bool:
        return self.log_destination is not None

@dataclass(frozen=True)
class RunContext:
    """Per-run values that must not be stored as module globals."""

    timestamp: str
    log_destination: Optional[str]
    log_file: Optional[str]
    error_file: Optional[str]
    output_file: Optional[str]

    @property
    def logging_enabled(self) -> bool:
        return self.log_destination is not None

@dataclass(frozen=True)
class DatasetPair:
    """One validated source/destination replication and its extra arguments."""

    source: str
    destination: str
    extra_arguments: tuple[str, ...]

@dataclass
class SyncoidAttemptResult:
    """Explicit result from one monitored Syncoid process attempt."""

    child: Any
    command: list[str]
    repeated_pattern: bool = False
    retry_without_resume: bool = False
    ignored_missing_destroy_snapshot: bool = False
