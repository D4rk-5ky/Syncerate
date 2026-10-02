"""Shared test helpers for Syncerate's dependency-free unittest suite."""

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
        raw = {
            "syncoid": {},
            "ssh": {},
            "mail": {},
            "logging": {},
            "runtime": {},
            "mqtt": {},
            "home_assistant": {},
        }

    values = {
        "config_path": "test.toml",
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
        "dry_run": False,
        "send_mail_on_success": True,
        "send_mqtt_on_success": True,
        "mqtt_json_status": False,
        "use_home_assistant": False,
        "use_ssh_agent": False,
        "ssh_agent_key_lifetime_seconds": 3600,
        "retry_broken_pipe": False,
        "continue_on_missing_dataset": False,
        "continue_without_resume": True,
        "broken_pipe_retry_count": 1,
        "broken_pipe_retry_wait_seconds": 0,
        "broker_address": "broker.example.test",
        "broker_port": 1883,
        "mqtt_username": "",
        "mqtt_password": "",
        "mqtt_topic": "syncerate/result",
        "mqtt_message": "ON",
        "mqtt_json_topic": "syncerate/status",
        "home_assistant_available": "syncerate/available",
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
