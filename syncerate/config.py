"""Configuration-file loading and Boolean option normalization."""

import configparser
from typing import Any

from .models import AppConfig

CONFIG_SECTION = "Syncerate Config"


def option_is_enabled(value: Any) -> bool:
    """Return True for supported enabled values used in the config file."""

    return str(value).strip().upper() in {"YES", "TRUE", "1", "ON"}

def load_app_config(config_path: str) -> AppConfig:
    """Read the INI file and return all startup settings as AppConfig."""

    raw_config = configparser.RawConfigParser()
    loaded_files = raw_config.read(config_path)

    if not loaded_files:
        raise FileNotFoundError(f"Could not read config file: {config_path}")

    if not raw_config.has_section(CONFIG_SECTION):
        raise configparser.NoSectionError(CONFIG_SECTION)

    log_destination_text = raw_config.get(
        CONFIG_SECTION,
        "LogDestination",
    ).strip()

    if log_destination_text.upper() == "NO":
        log_destination = None
    else:
        log_destination = log_destination_text
        if not log_destination.endswith("/"):
            log_destination += "/"

    broken_pipe_retry_count = raw_config.getint(
        CONFIG_SECTION,
        "BrokenPipeRetryCount",
        fallback=1,
    )

    if broken_pipe_retry_count < 0:
        raise ValueError(
            "BrokenPipeRetryCount must be zero or a positive whole number"
        )

    broken_pipe_retry_wait_seconds = raw_config.getint(
        CONFIG_SECTION,
        "BrokenPipeRetryWaitSeconds",
        fallback=10,
    )

    if broken_pipe_retry_wait_seconds < 0:
        raise ValueError(
            "BrokenPipeRetryWaitSeconds must be zero or a positive whole number"
        )

    return AppConfig(
        config_path=config_path,
        raw_config=raw_config,
        mail_option=raw_config.get(CONFIG_SECTION, "Mail"),
        system_option=raw_config.get(CONFIG_SECTION, "SystemAction"),
        use_mqtt=option_is_enabled(
            raw_config.get(CONFIG_SECTION, "Use_MQTT", fallback="No")
        ),
        datetime_format=raw_config.get(CONFIG_SECTION, "DateTime"),
        log_destination=log_destination,
        backup_title=raw_config.get(
            CONFIG_SECTION,
            "BackupTitle",
            fallback="",
        ).strip(),
        backup_comment=raw_config.get(
            CONFIG_SECTION,
            "BackupComment",
            fallback="",
        ).strip(),
        source_list_path=raw_config.get(CONFIG_SECTION, "SourceListPath"),
        destination_list_path=raw_config.get(CONFIG_SECTION, "DestListPath"),
        password_option=raw_config.get(CONFIG_SECTION, "PassWord"),
        syncoid_command=raw_config.get(CONFIG_SECTION, "SyncoidCommand"),
        retry_broken_pipe=option_is_enabled(
            raw_config.get(CONFIG_SECTION, "RetryBrokenPipe", fallback="No")
        ),
        broken_pipe_retry_count=broken_pipe_retry_count,
        broken_pipe_retry_wait_seconds=broken_pipe_retry_wait_seconds,
    )
