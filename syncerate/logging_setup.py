"""Per-run timestamp, log-file paths, and logger configuration."""

import datetime
import logging
import os
import sys

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

        if app_config.backup_title:
            logger.info("Backup title    :   %s", app_config.backup_title)

        if app_config.backup_comment:
            logger.info("Backup comment  :   %s", app_config.backup_comment)

    logger.info("")
    logger.info("The Date used for Log Files  :   %s", run_context.timestamp)

    for section in app_config.raw_config.sections():
        logger.info("")
        logger.info("----------")
        logger.info("")
        logger.info("These are the imported variables in the config file")
        logger.info('Omitting the "PassWord" since it shouldten be logged')
        logger.info("")
        logger.info(section)
        logger.info("")

        for option in app_config.raw_config.options(section):
            if option in ["password", "mqtt_username", "mqtt_password"]:
                continue

            if option in ["use_homeassistant", "homeassistant_available"]:
                continue

            if not app_config.use_mqtt and option in [
                "broker_address",
                "broker_port",
                "mqtt_topic",
                "mqtt_message",
            ]:
                continue

            value = app_config.raw_config.get(section, option)
            logger.info("%s %s", option, value)
            logger.info("")

    if app_config.syncoid_command.startswith("syncoid"):
        logger.info("The syncoid command is in use")
        logger.info("")
        logger.info("----------")
        logger.info("")
