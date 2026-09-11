"""Shared test helpers for Syncerate's dependency-free unittest suite."""

import configparser
import logging
from pathlib import Path
from typing import Any

from syncerate.models import AppConfig, RunContext


def make_logger(name: str = "syncerate-test") -> logging.Logger:
    """Return an isolated logger that discards output unless a test adds a handler."""

    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger


def make_config(**overrides: Any) -> AppConfig:
    """Build a minimal AppConfig with safe test defaults."""

    raw = overrides.pop("raw_config", None)
    if raw is None:
        raw = configparser.RawConfigParser()
        raw.add_section("Syncerate Config")

    values = {
        "config_path": "test.cfg",
        "raw_config": raw,
        "mail_option": "No",
        "system_option": "No",
        "use_mqtt": False,
        "datetime_format": "%Y-%m-%d_%H_%M_%S",
        "log_destination": None,
        "backup_title": "",
        "backup_comment": "",
        "source_list_path": "source-list",
        "destination_list_path": "dest-list",
        "password_option": "No",
        "syncoid_command": "syncoid SourceDataSet DestDataSet",
        "mqtt_json_status": False,
        "use_home_assistant": False,
        "use_ssh_agent": False,
        "ssh_agent_key_lifetime_seconds": 3600,
        "retry_broken_pipe": False,
        "broken_pipe_retry_count": 1,
        "broken_pipe_retry_wait_seconds": 0,
    }
    values.update(overrides)
    return AppConfig(**values)


def no_logging_context() -> RunContext:
    """Return a RunContext with file logging disabled."""

    return RunContext(
        timestamp="test",
        log_destination=None,
        log_file=None,
        error_file=None,
        output_file=None,
    )


def write_executable(path: Path, body: str) -> str:
    """Write a small executable Python helper and return its path as text."""

    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return str(path)
