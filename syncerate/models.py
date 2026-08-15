"""Dataclasses that carry configuration and per-run state explicitly."""

import configparser
from dataclasses import dataclass, field
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
    mqtt_json_status: bool = False
    use_ssh_agent: bool = False
    ssh_agent_key_lifetime_seconds: int = 3600
    retry_broken_pipe: bool = False
    broken_pipe_retry_count: int = 1
    broken_pipe_retry_wait_seconds: int = 10

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
    ignored_missing_destroy_snapshot: bool = False
    broken_pipe_detected: bool = False


@dataclass
class SSHAgentSession:
    """One isolated per-run ssh-agent and the environment used by Syncoid."""

    process: Any
    temp_directory: str
    socket_path: str
    environment: dict[str, str]
    identity_file: str
    ssh_add_path: str
    key_lifetime_seconds: int


@dataclass
class ReplicationSummary:
    """Non-fatal conditions collected while processing the dataset list."""

    broken_pipe_failed_datasets: list[DatasetPair] = field(default_factory=list)

    @property
    def has_broken_pipe_warning(self) -> bool:
        """Return True when at least one dataset exhausted its Broken Pipe retries."""

        return bool(self.broken_pipe_failed_datasets)
