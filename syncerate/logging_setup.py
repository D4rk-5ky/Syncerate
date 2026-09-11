"""Per-run timestamp, log-file paths, and logger configuration."""

import datetime
import logging
import os
import sys
from typing import Optional

from .config import CONFIG_SECTION
from .models import AppConfig, RunContext


def create_run_context(app_config: AppConfig) -> RunContext:
    """Create the timestamp and optional log paths for this invocation."""

    timestamp = datetime.datetime.now().strftime(app_config.datetime_format)

    if not app_config.logging_enabled:
        return RunContext(
            timestamp=timestamp,
            log_destination=None,
            log_file=None,
            error_file=None,
            output_file=None,
        )

    destination = app_config.log_destination
    assert destination is not None

    prefix = destination + "Syncerate-" + timestamp
    return RunContext(
        timestamp=timestamp,
        log_destination=destination,
        log_file=prefix + ".log",
        error_file=prefix + ".err",
        output_file=prefix + ".out",
    )


def get_logger(run_context: RunContext) -> logging.Logger:
    """Create terminal logging and optional per-run .log/.err handlers."""

    logger = logging.getLogger("syncerate")
    logger.setLevel(logging.INFO)

    for existing_handler in list(logger.handlers):
        existing_handler.close()
        logger.removeHandler(existing_handler)

    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)
    logger.addHandler(stream_handler)

    if run_context.logging_enabled:
        assert run_context.log_destination is not None
        assert run_context.log_file is not None
        assert run_context.error_file is not None

        os.makedirs(run_context.log_destination, exist_ok=True)

        info_handler = logging.FileHandler(run_context.log_file, mode="w")
        info_handler.setFormatter(formatter)
        info_handler.setLevel(logging.INFO)
        logger.addHandler(info_handler)

        error_handler = logging.FileHandler(run_context.error_file, mode="w")
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        logger.addHandler(error_handler)

    return logger


def get_console_logger() -> logging.Logger:
    """Return a terminal-only logger for failures before RunContext exists."""

    return get_logger(
        RunContext(
            timestamp="",
            log_destination=None,
            log_file=None,
            error_file=None,
            output_file=None,
        )
    )


def _format_multiline_value_lines(prefix: str, value: str) -> list[str]:
    """Return aligned physical lines for one labelled multiline value."""

    value_lines = value.splitlines() or [""]
    formatted_lines = [f"{prefix}{value_lines[0]}"]
    continuation_prefix = " " * len(prefix)
    formatted_lines.extend(
        f"{continuation_prefix}{line}" for line in value_lines[1:]
    )
    return formatted_lines


def log_multiline_value(
    logger: logging.Logger,
    prefix: str,
    value: str,
) -> None:
    """Log a possibly multiline value while prefixing every physical log line."""

    for line in _format_multiline_value_lines(prefix, value):
        logger.info("%s", line)


def log_backup_metadata(app_config: AppConfig, logger: logging.Logger) -> None:
    """Log the optional backup title and multiline comment consistently."""

    if app_config.backup_title:
        log_multiline_value(logger, "Backup title    :   ", app_config.backup_title)

    if app_config.backup_title and app_config.backup_comment:
        logger.info("")

    if app_config.backup_comment:
        log_multiline_value(logger, "Backup comment  :   ", app_config.backup_comment)


def format_runtime_duration(elapsed_seconds: float) -> str:
    """Format monotonic elapsed time as HH:MM:SS.mmm."""

    total_milliseconds = max(0, round(elapsed_seconds * 1000))
    total_seconds, milliseconds = divmod(total_milliseconds, 1000)
    minutes_total, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes_total, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def format_final_run_summary(
    app_config: Optional[AppConfig],
    elapsed_seconds: float,
) -> str:
    """Return the final summary as plain text for logs and email bodies."""

    lines = ["Final run summary", ""]
    metadata_written = False

    if app_config is not None and app_config.backup_title:
        lines.extend(
            _format_multiline_value_lines(
                "Backup title    :   ", app_config.backup_title
            )
        )
        metadata_written = True

    if (
        app_config is not None
        and app_config.backup_title
        and app_config.backup_comment
    ):
        lines.append("")

    if app_config is not None and app_config.backup_comment:
        lines.extend(
            _format_multiline_value_lines(
                "Backup comment  :   ", app_config.backup_comment
            )
        )
        metadata_written = True

    # Keep one visible blank line between the optional backup metadata and the
    # runtime, matching the terminal/log layout requested for email as well.
    if metadata_written:
        lines.append("")

    lines.append(f"Total runtime   :   {format_runtime_duration(elapsed_seconds)}")
    return "\n".join(lines)


def log_final_run_summary(
    app_config: Optional[AppConfig],
    elapsed_seconds: float,
    logger: logging.Logger,
) -> None:
    """Log the shared final summary to terminal and the optional .log file."""

    logger.info("")
    logger.info("----------")
    logger.info("")

    for line in format_final_run_summary(app_config, elapsed_seconds).splitlines():
        logger.info("%s", line)

    logger.info("")
    logger.info("----------")
    logger.info("")


def log_startup_configuration(
    app_config: AppConfig,
    run_context: RunContext,
    logger: logging.Logger,
) -> None:
    """Log startup information while deliberately hiding credentials."""

    if not run_context.logging_enabled:
        logger.info("")
        logger.info("----------")
        logger.info("Logging has beend disabled")
        logger.info("")
        logger.info("Only writing to terminal")

    logger.info("")
    logger.info("----------")
    logger.info("")
    logger.info("Config file destination  :   %s", app_config.config_path)

    if app_config.backup_title or app_config.backup_comment:
        logger.info("")
        logger.info("----------")
        logger.info("")
        logger.info("Backup information")
        logger.info("")

        log_backup_metadata(app_config, logger)

    logger.info("")
    logger.info("The Date used for Log Files  :   %s", run_context.timestamp)

    # Only this section is consumed by Syncerate. Do not echo unrelated INI
    # sections into logs because a shared file may contain credentials for
    # another application. Also suppress common secret-like option names in
    # addition to Syncerate's known credential fields.
    section = CONFIG_SECTION
    logger.info("")
    logger.info("----------")
    logger.info("")
    logger.info("These are the imported variables in the config file")
    logger.info('Omitting password/credential values from logging')
    logger.info("")
    logger.info(section)
    logger.info("")

    for option in app_config.raw_config.options(section):
        if option in ["password", "mqtt_username", "mqtt_password"]:
            continue

        if any(
            marker in option
            for marker in ["password", "secret", "token", "credential", "api_key", "apikey"]
        ):
            continue

        if option in ["use_homeassistant", "homeassistant_available"]:
            continue

        if (
            not (app_config.use_mqtt or app_config.mqtt_json_status)
            and option in ["broker_address", "broker_port"]
        ):
            continue

        if not app_config.use_mqtt and option in ["mqtt_topic", "mqtt_message"]:
            continue

        if not app_config.mqtt_json_status and option == "mqtt_json_topic":
            continue

        value = app_config.raw_config.get(section, option)
        log_multiline_value(logger, f"{option} ", value)
        logger.info("")

    if app_config.syncoid_command.startswith("syncoid"):
        logger.info("The syncoid command is in use")
        logger.info("")
        logger.info("----------")
        logger.info("")
