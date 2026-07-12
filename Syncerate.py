#!/usr/bin/python3

"""Run paired Syncoid replications from a configuration file.

Version 0.4.6 keeps the application in one file while making all runtime
state explicit. Importing this module defines classes and functions only; it
does not parse arguments, read configuration files, create logs, request a
password, or start Syncoid.
"""

import argparse
import configparser
import datetime
import logging
import os
import pwd
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from getpass import getpass
from typing import Any, Optional, Sequence

import pexpect


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

VERSION = "0.4.6"
CONFIG_SECTION = "Syncerate Config"


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


def option_is_enabled(value: Any) -> bool:
    """Return True for supported enabled values used in the config file."""

    return str(value).strip().upper() in {"YES", "TRUE", "1", "ON"}


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Create and parse Syncerate command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Iterate though 2 lists of ZFS DataSets with Syncoid"
    )
    parser.add_argument(
        "--conf",
        "-c",
        type=str,
        required=True,
        help="The destination for the config file",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    return parser.parse_args(argv)


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
    )


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


def backup_header_text(app_config: AppConfig) -> str:
    """Return optional backup title/comment text used in email bodies."""

    lines: list[str] = []

    if app_config.backup_title:
        lines.append("Backup title:")
        lines.append(app_config.backup_title)
        lines.append("")

    if app_config.backup_comment:
        lines.append("Backup comment:")
        lines.append(app_config.backup_comment)
        lines.append("")

    if lines:
        lines.append("----------")
        lines.append("")

    return "\n".join(lines)


def send_mail(
    subject: str,
    body: str,
    recipient: str,
    attachment_files: Optional[list[str]] = None,
) -> tuple[int, str]:
    """Send one message through the local mail command."""

    mail_command = ["mail", "-s", subject, recipient]

    if attachment_files:
        for attachment_file in attachment_files:
            mail_command.extend(["--attach", attachment_file])

    process = subprocess.Popen(
        mail_command,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _, stderr_output = process.communicate(input=body.encode())
    return process.returncode, stderr_output.decode().strip()


def WasMailSent(
    mail_exit_code: int,
    popen_stderr: str,
    logger: logging.Logger,
) -> None:
    """Log whether the local mail process accepted the message."""

    if mail_exit_code == 0:
        logger.info("")
        logger.info("----------")
        logger.info("")
        logger.info("Mail was send succesfully")
    else:
        logger.error("")
        logger.error("----------")
        logger.error("")
        logger.error("There was an error sending the mail")
        logger.error("This is what popen said")
        logger.error("")
        logger.error(popen_stderr)
        logger.error("")
        logger.error("----------")


def MailTo(
    app_config: AppConfig,
    run_context: RunContext,
    logger: logging.Logger,
    Exit_Code: Optional[int] = None,
    SynCoidFail: Optional[int] = None,
    MQTT_Fail: Optional[int] = None,
) -> None:
    """Build and send the same success/error mail variants as earlier releases.

    This function no longer terminates the process. The top-level main()
    exception boundary owns the final exit code.
    """

    if not app_config.mail_enabled:
        return

    recipient = app_config.mail_option

    logger.info("")
    logger.info("----------")
    logger.info("")
    logger.info("There is an option to send a mail")

    logging_enabled = run_context.logging_enabled
    log_file = run_context.log_file
    error_file = run_context.error_file
    output_file = run_context.output_file

    if Exit_Code == EXIT_OK:
        if logging_enabled:
            assert log_file is not None
            assert output_file is not None

            subject = "Successful Syncerate.py run - No errors found (Attaching logs)"
            attachment_files = [log_file, output_file]

            with open(log_file, "r", encoding="utf-8") as opened_log:
                log_contents = opened_log.read()

            body = (
                backup_header_text(app_config)
                + "----------\n\n.log file\n\n----------\n\n"
                + log_contents
                + "\n\n----------"
            )
            mail_exit_code, stderr_output = send_mail(
                subject,
                body,
                recipient,
                attachment_files,
            )
        else:
            subject_and_body = (
                "Successful Syncerate.py run - No errors found (Logs Disabled)"
            )
            mail_exit_code, stderr_output = send_mail(
                subject_and_body,
                backup_header_text(app_config) + subject_and_body,
                recipient,
            )

        WasMailSent(mail_exit_code, stderr_output, logger)
        return

    if SynCoidFail is not None:
        if logging_enabled:
            assert log_file is not None
            assert error_file is not None

            subject = "Error running Syncerate.py - Syncoid error occurred (Attaching logs)"
            attachment_files = [log_file, error_file]
            if output_file is not None and os.path.isfile(output_file):
                attachment_files.append(output_file)

            body = backup_header_text(app_config)
            with open(error_file, "r", encoding="utf-8") as opened_error:
                error_contents = opened_error.read()
            body += (
                "----------\n\n.err file\n\n----------\n\n"
                + error_contents
                + "\n\n"
            )

            if output_file is not None and os.path.isfile(output_file):
                with open(output_file, "r", encoding="utf-8") as opened_output:
                    output_contents = opened_output.read()
                body += "----------\n\n.out file\n" + output_contents

            mail_exit_code, stderr_output = send_mail(
                subject,
                body,
                recipient,
                attachment_files,
            )
        else:
            subject_and_body = (
                "Error running Syncerate.py - Syncoid error occurred (Logs Disabled)"
            )
            mail_exit_code, stderr_output = send_mail(
                subject_and_body,
                backup_header_text(app_config) + subject_and_body,
                recipient,
            )

        WasMailSent(mail_exit_code, stderr_output, logger)
        return

    if MQTT_Fail is not None:
        if logging_enabled:
            assert log_file is not None
            assert error_file is not None

            subject = "Error sending MQTT message - (Attaching logs)"
            attachment_files = [log_file, error_file]
            if output_file is not None and os.path.isfile(output_file):
                attachment_files.append(output_file)

            body = backup_header_text(app_config)
            with open(error_file, "r", encoding="utf-8") as opened_error:
                error_contents = opened_error.read()
            body += (
                "----------\n\n.err file\n\n----------\n\n"
                + error_contents
                + "\n\n"
            )

            if output_file is not None and os.path.isfile(output_file):
                with open(output_file, "r", encoding="utf-8") as opened_output:
                    output_contents = opened_output.read()
                body += "----------\n\n.out file\n" + output_contents

            mail_exit_code, stderr_output = send_mail(
                subject,
                body,
                recipient,
                attachment_files,
            )
        else:
            subject_and_body = "Error sending MQTT message - (Logs Disabled)"
            mail_exit_code, stderr_output = send_mail(
                subject_and_body,
                backup_header_text(app_config) + subject_and_body,
                recipient,
            )

        WasMailSent(mail_exit_code, stderr_output, logger)
        return

    if Exit_Code is not None and Exit_Code != EXIT_OK:
        if logging_enabled:
            assert log_file is not None
            assert error_file is not None

            subject = "Error running Syncerate.py - This was a script error (Attaching logs)"
            attachment_files = [log_file, error_file]
            if output_file is not None and os.path.isfile(output_file):
                attachment_files.append(output_file)

            body = backup_header_text(app_config)
            with open(error_file, "r", encoding="utf-8") as opened_error:
                error_contents = opened_error.read()
            body += (
                "----------\n\n.err file\n\n----------\n\n"
                + error_contents
                + "\n\n"
            )

            if output_file is not None and os.path.isfile(output_file):
                with open(output_file, "r", encoding="utf-8") as opened_output:
                    output_contents = opened_output.read()
                body += "----------\n\n.out file\n" + output_contents

            mail_exit_code, stderr_output = send_mail(
                subject,
                body,
                recipient,
                attachment_files,
            )
        else:
            subject_and_body = (
                "Error running Syncerate.py - This was a script error (Logs Disabled)"
            )
            mail_exit_code, stderr_output = send_mail(
                subject_and_body,
                backup_header_text(app_config) + subject_and_body,
                recipient,
            )

        WasMailSent(mail_exit_code, stderr_output, logger)


def send_mqtt_messages(
    app_config: AppConfig,
    logger: logging.Logger,
) -> None:
    """Publish MQTT/HA messages, importing paho only when this runs."""

    try:
        from paho.mqtt import publish
    except ImportError as exc:
        logger.error(
            "MQTT is enabled, but the optional paho-mqtt package could not be loaded: %s",
            exc,
        )
        raise SyncerateError(
            "MQTT is enabled but paho-mqtt could not be loaded",
            EXIT_MQTT_ERROR,
            kind="mqtt",
        ) from exc

    raw_config = app_config.raw_config
    broker_address = raw_config.get(CONFIG_SECTION, "broker_address")
    broker_port = raw_config.getint(CONFIG_SECTION, "broker_port")
    mqtt_username = raw_config.get(
        CONFIG_SECTION,
        "mqtt_username",
        fallback="",
    ).strip()
    mqtt_password = raw_config.get(
        CONFIG_SECTION,
        "mqtt_password",
        fallback="",
    )

    auth = None
    if mqtt_username:
        auth = {
            "username": mqtt_username,
            "password": mqtt_password,
        }

    messages: list[dict[str, Any]] = []

    use_home_assistant = option_is_enabled(
        raw_config.get(
            CONFIG_SECTION,
            "Use_HomeAssistant",
            fallback="No",
        )
    )

    if use_home_assistant:
        messages.append(
            {
                "topic": raw_config.get(
                    CONFIG_SECTION,
                    "HomeAssistant_Available",
                ),
                "payload": "online",
                "retain": True,
                "qos": 0,
            }
        )

    messages.append(
        {
            "topic": raw_config.get(CONFIG_SECTION, "mqtt_topic"),
            "payload": raw_config.get(CONFIG_SECTION, "mqtt_message"),
            "retain": True,
            "qos": 0,
        }
    )

    try:
        publish.multiple(
            messages,
            hostname=broker_address,
            port=broker_port,
            auth=auth,
        )
        logger.info("MQTT message(s) published successfully")
    except Exception as exc:
        logger.exception("Failed publishing MQTT message(s)")
        raise SyncerateError(
            "Failed publishing MQTT message(s)",
            EXIT_MQTT_ERROR,
            kind="mqtt",
        ) from exc


def SystemAction(app_config: AppConfig, logger: logging.Logger) -> None:
    """Run the configured successful-run shell command."""

    if app_config.mail_enabled:
        logger.info("")
        logger.info("----------")
        logger.info("")
        logger.info("The system has an option after the script finishes")
        logger.info("")
        logger.info("The options is")
        logger.info("")
        logger.info(app_config.system_option)
        logger.info("")
        logger.info("Gonna sleep for 2 minutes to insure mail is sent")
        logger.info("")
        logger.info("Then execute the command\t:\t" + app_config.system_option)
        logger.info("")
        logger.info("----------")

        time.sleep(120)

        try:
            subprocess.run(app_config.system_option, shell=True, check=False)
        except Exception:
            logger.exception("Failed running SystemAction")

    elif app_config.system_action_enabled:
        logger.info("")
        logger.info("----------")
        logger.info("")
        logger.info("The system has an option after the script finishes")
        logger.info("")
        logger.info("The options is")
        logger.info("")
        logger.info(app_config.system_option)
        logger.info("")
        logger.info("No mail option chosen")
        logger.info("")
        logger.info("Gonna execute the command\t:\t" + app_config.system_option)
        logger.info("")
        logger.info("----------")

        try:
            subprocess.run(app_config.system_option, shell=True, check=False)
        except Exception:
            logger.exception("Failed running SystemAction")


def successfull_run(
    app_config: AppConfig,
    run_context: RunContext,
    logger: logging.Logger,
) -> None:
    """Run the existing success-stage MQTT, mail, and system actions."""

    logger.info("")
    logger.info("----------")
    logger.info("")
    logger.info("The Script ended successfully")
    logger.info("")
    logger.info(
        "Now going over MAIL, MQTT and System Option, if option is set in the .cfg file"
    )
    logger.info("")
    logger.info("Errors for these can still be raised, at this point of the script")
    logger.info("")

    if run_context.logging_enabled:
        assert run_context.output_file is not None
        with open(run_context.output_file, "a", encoding="utf-8") as output_file:
            lines_of_text = [
                "",
                "----------",
                "",
                "The Script ended successfully",
                "",
                "Now going over MAIL, MQTT and System Option, if option is set in the .cfg file",
                "",
                "Errors for these can still be raised, at this point of the script",
                "",
                "----------",
                "",
            ]

            for line in lines_of_text:
                output_file.write(line + "\n")

    if app_config.use_mqtt:
        send_mqtt_messages(app_config, logger)

    if app_config.mail_enabled:
        MailTo(app_config, run_context, logger, Exit_Code=EXIT_OK)

    if app_config.system_action_enabled:
        SystemAction(app_config, logger)


def missmatchinglists(
    Lenght: bool,
    Names: bool,
    logger: logging.Logger,
) -> None:
    """Log source/destination list validation failure and raise exit code 1."""

    if Lenght is True:
        logger.error("")
        logger.error("----------")
        logger.error("")
        logger.error("The number of items in each list does not match")
        logger.error("Check the terminal or .err log")
        logger.error("exiting - error code 1")

    if Names is True:
        logger.error("")
        logger.error("----------")
        logger.error("")
        logger.error("There are datasets on source and destination which ends doesnt match up")
        logger.error("Check the terminal or .err log")
        logger.error("exiting - error code 1")

    raise SyncerateError(
        "Source and destination list validation failed",
        EXIT_LIST_ERROR,
        kind="list",
    )


def read_dataset_list(path: str) -> list[str]:
    """Read active dataset-list lines, ignoring blanks and comments."""

    with open(path, "r", encoding="utf-8") as dataset_file:
        return [
            line.strip()
            for line in dataset_file
            if line.strip() and not line.strip().startswith("#")
        ]


def parse_destination_line(line: str) -> tuple[str, list[str]]:
    """Parse one destination and its optional per-destination arguments."""

    if ": " not in line:
        return line, []

    destination_dataset, extra_args_text = line.rsplit(": ", 1)
    destination_dataset = destination_dataset.strip()
    extra_args_text = extra_args_text.strip()

    if not extra_args_text:
        return destination_dataset, []

    try:
        extra_args = shlex.split(extra_args_text)
    except ValueError as exc:
        raise ValueError(
            "Could not parse extra arguments for destination line:\n"
            f"{line}\n"
            f"shlex error: {exc}"
        ) from exc

    return destination_dataset, extra_args


def parse_destination_list(
    destination_lines: list[str],
) -> tuple[list[str], list[list[str]]]:
    """Return destination datasets and matching per-destination argument lists."""

    destination_datasets: list[str] = []
    destination_extra_arguments: list[list[str]] = []

    for line in destination_lines:
        destination_dataset, extra_arguments = parse_destination_line(line)
        destination_datasets.append(destination_dataset)
        destination_extra_arguments.append(extra_arguments)

    return destination_datasets, destination_extra_arguments


def load_dataset_pairs(
    app_config: AppConfig,
    logger: logging.Logger,
) -> list[DatasetPair]:
    """Load, log, validate, and combine both dataset files."""

    source_lines = read_dataset_list(app_config.source_list_path)

    logger.info("Items in the Source list    :   %s", source_lines)
    logger.info("Number of items in the Source list    :   %i", len(source_lines))
    logger.info("")

    destination_lines_raw = read_dataset_list(app_config.destination_list_path)

    try:
        destination_lines, destination_extra_arguments = parse_destination_list(
            destination_lines_raw
        )
    except ValueError as exc:
        logger.error("%s", exc)
        raise SyncerateError(
            str(exc),
            EXIT_LIST_ERROR,
            kind="list",
        ) from exc

    logger.info("Raw items in the Destination list    :   %s", destination_lines_raw)
    logger.info("Parsed Destination datasets          :   %s", destination_lines)
    logger.info(
        "Parsed Destination extra args        :   %s",
        destination_extra_arguments,
    )
    logger.info(
        "Number of items in the Destination list    :   %i",
        len(destination_lines),
    )
    logger.info("")

    if len(source_lines) == len(destination_lines):
        logger.info("The Source and Dest files has the same number of items")
        logger.info("")
    else:
        missmatchinglists(Lenght=True, Names=False, logger=logger)

    lists_check_out = True
    for source, destination in zip(source_lines, destination_lines):
        if source.rpartition("/")[-1] == destination.rpartition("/")[-1]:
            logger.info("The end of this Source and Destination Datasets matches:")
            logger.info("Source :   %s", source)
            logger.info("Dest   :   %s", destination)
            logger.info("")
        else:
            logger.error(
                "The end of this Source and Destination Datasets end does not match:"
            )
            logger.error("Source :   %s", source)
            logger.error("Dest   :   %s", destination)
            logger.error("")
            lists_check_out = False

    if lists_check_out:
        logger.info("All datasets ends matches")
        logger.info("continuing")
    else:
        missmatchinglists(Lenght=False, Names=True, logger=logger)

    return [
        DatasetPair(
            source=source,
            destination=destination,
            extra_arguments=tuple(extra_arguments),
        )
        for source, destination, extra_arguments in zip(
            source_lines,
            destination_lines,
            destination_extra_arguments,
        )
    ]


def resolve_password(
    app_config: AppConfig,
    logger: logging.Logger,
) -> Optional[str]:
    """Resolve No, Ask, or a literal password/passphrase from the config."""

    password_option = app_config.password_option

    if password_option.upper() == "ASK":
        password = getpass("PLz. insert a desiret password if needed :    ")
        logger.info("")
        logger.info("----------")
        logger.info("")
        logger.info("The Password has been manualy added, not written to log")
        logger.info("")
        return password

    if password_option.upper() == "NO":
        logger.info("")
        logger.info("----------")
        logger.info("")
        logger.info("No password is in use")
        return None

    logger.info("")
    logger.info("----------")
    logger.info("")
    logger.info("Password is in the config file, not written to log")
    return password_option


def safe_text(value: Any) -> str:
    """Convert optional pexpect output values to safe text."""

    if value is None:
        return ""
    return str(value)


def close_child_logfile(
    child: Any,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Flush and close a pexpect logfile without closing the child process."""

    if child is None:
        return

    logfile = getattr(child, "logfile", None)
    if logfile is None:
        return

    try:
        logfile.flush()
        logfile.close()
    except Exception:
        if logger is not None:
            logger.exception("Could not close pexpect logfile cleanly")
    finally:
        child.logfile = None


def die(
    child: Any = None,
    errstr: Optional[str] = None,
    error_code: Optional[int] = None,
    SynCoidFail: Optional[int] = None,
    MQTT_Fail: Optional[int] = None,
    SynCoidFailChild: Any = None,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Convert the old internal exit paths into one SyncerateError exception."""

    if error_code is not None:
        exit_code = int(error_code)
    elif SynCoidFail is not None:
        exit_code = int(SynCoidFail)
    elif MQTT_Fail is not None:
        exit_code = int(MQTT_Fail)
    else:
        exit_code = EXIT_LIST_ERROR

    if child is not None:
        child_before = safe_text(getattr(child, "before", ""))
        child_warning = safe_text(getattr(child, "after", "")) + safe_text(
            getattr(child, "buffer", "")
        )

        try:
            child.terminate(force=True)
        except Exception:
            if logger is not None:
                logger.exception("Could not terminate child process cleanly")

        close_child_logfile(child, logger)

        raise SyncerateError(
            errstr or "Known Syncoid error",
            exit_code,
            kind="known_child",
            child_before=child_before,
            child_warning=child_warning,
        )

    if SynCoidFail is not None:
        syncoid_before = ""
        if SynCoidFailChild is not None:
            syncoid_before = safe_text(getattr(SynCoidFailChild, "before", ""))

        raise SyncerateError(
            "Unknown Syncoid crash",
            exit_code,
            kind="syncoid",
            syncoid_before=syncoid_before,
        )

    if MQTT_Fail is not None:
        raise SyncerateError(
            "MQTT error",
            exit_code,
            kind="mqtt",
        )

    raise SyncerateError(
        errstr or "Script error",
        exit_code,
        kind="script",
    )


def log_syncerate_error(
    error: SyncerateError,
    logger: logging.Logger,
) -> None:
    """Write the old die() diagnostics at the top-level error boundary."""

    if error.kind == "list":
        return

    logger.error("")
    logger.error("----------")
    logger.error("")

    if error.kind == "known_child":
        logger.error("This was a crash known by the script")
        logger.error("")
        logger.error("Check the logs to see what could be the problem")
        logger.error("If no logs exist, enable them to track down the problem")
        logger.error("")

        if error.message:
            logger.error(error.message)
            logger.error("")

        logger.error("This is the last part of Syncoid output:")
        logger.error(error.child_before)
        logger.error("")
        logger.error("This is the warning/error:")
        logger.error(error.child_warning)
        logger.error("")
        logger.error("This is the script exit code: %s", error.exit_code)

    elif error.kind == "syncoid":
        logger.error("This was an unknown Syncoid crash")
        logger.error("Syncoid exit code: %s", error.exit_code)

        if error.syncoid_before:
            logger.error("")
            logger.error("This is the last part of Syncoid output:")
            logger.error(error.syncoid_before)

    elif error.kind == "mqtt":
        logger.error("This was an MQTT error")
        logger.error("MQTT exit code: %s", error.exit_code)

    else:
        logger.error("This was a script error")
        logger.error("Exit code: %s", error.exit_code)

    logger.error("")
    logger.error("----------")
    logger.error("")


def log_command_debug(command_list: list[str], logger: logging.Logger) -> None:
    """Log shell-style, raw-list, and argument-by-argument command views."""

    logger.info("")
    logger.info("Syncoid command debug:")
    logger.info("")
    logger.info("Shell-style command:")
    logger.info("%s", shlex.join(command_list))
    logger.info("")
    logger.info("Raw Python argv:")
    logger.info("%r", command_list)
    logger.info("")
    logger.info("Individual arguments:")
    logger.info("Argument count: %s", len(command_list))

    for number, argument in enumerate(command_list):
        logger.info("argv[%s] = %r", number, argument)

    logger.info("")


def build_syncoid_command(
    command_template: str,
    source_dataset: str,
    destination_dataset: str,
    extra_args: Optional[Sequence[str]] = None,
) -> list[str]:
    """Build a safe argv-style command while preserving dataset spaces."""

    if extra_args is None:
        extra_args = []

    command_parts = shlex.split(command_template)
    command_parts = [
        part.replace("SourceDataSet", source_dataset).replace(
            "DestDataSet",
            destination_dataset,
        )
        for part in command_parts
    ]
    command_parts.extend(extra_args)
    return command_parts


def effective_user_name() -> str:
    """Return the username belonging to Syncerate's effective local UID."""

    try:
        return pwd.getpwuid(os.geteuid()).pw_name
    except (KeyError, OSError):
        return f"UID {os.geteuid()}"


def ssh_command(
    syncoid_command: list[str],
    password: Optional[str],
    run_context: RunContext,
    logger: logging.Logger,
) -> SyncoidAttemptResult:
    """Start and monitor one Syncoid process and return explicit flags."""

    repeated_pattern = False
    ignored_missing_destroy_snapshot = False
    retry_without_resume = False
    modified_command = list(syncoid_command)

    logger.info("")
    logger.info(
        "Local Syncoid process identity: %s (effective UID %s)",
        effective_user_name(),
        os.geteuid(),
    )
    logger.info(
        "Local ZFS commands inherit this identity; remote ZFS commands use the SSH user in the dataset endpoint."
    )
    logger.info("")

    if run_context.logging_enabled:
        assert run_context.output_file is not None
        with open(run_context.output_file, "a", encoding="utf-8") as output_file:
            for line in ["", "----------", ""]:
                output_file.write(line + "\n")

    child = pexpect.spawn(
        syncoid_command[0],
        syncoid_command[1:],
        timeout=None,
        encoding="utf-8",
    )

    output_handle = None
    if run_context.logging_enabled:
        assert run_context.output_file is not None
        output_handle = open(run_context.output_file, "a", encoding="utf-8")
        child.logfile = output_handle

    PATTERN_HOSTKEY = 0
    PATTERN_NO_DESTROY_SNAP = 1
    PATTERN_PERMISSION_DENIED = 2
    PATTERN_TIMEOUT = 3
    PATTERN_REFUSED = 4
    PATTERN_PASSPHRASE = 5
    PATTERN_EOF = 6
    PATTERN_WARN_SKIPPING = 7
    PATTERN_NO_RESUME = 8
    PATTERN_RESUME_UNAVAILABLE = 9
    PATTERN_GENERIC_WARN = 10
    PATTERN_PASSWORD = 11

    patterns = [
        "Are you sure you want to continue connecting",
        "could not find any snapshots to destroy; check snapshot names.",
        "Permission denied",
        "Connection timed out",
        "Connection refused",
        "passphrase",
        pexpect.EOF,
        "WARN Skipping dataset",
        "used in the initial send no longer exists",
        r"WARN: ZFS resume feature not available on (?:source|target|source and target) machines? - sync will continue without resume support\.",
        "WARN|WARNING",
        "password",
    ]

    max_pattern_executions = 5
    pattern_count = {index: 0 for index in range(len(patterns))}

    while True:
        index = child.expect(patterns)
        pattern_count[index] += 1

        if pattern_count[index] > max_pattern_executions:
            logger.error("")
            logger.error(
                "Pattern '%s' has been executed more than %s times.",
                patterns[index],
                max_pattern_executions,
            )
            logger.error("")
            repeated_pattern = True
            break

        if index == PATTERN_HOSTKEY:
            child.sendline("yes")

        elif index == PATTERN_NO_DESTROY_SNAP:
            logger.info("")
            logger.info("----------")
            logger.info("")
            logger.info(
                "Syncoid wanted to delete a syncoid-created snapshot that no longer exists."
            )
            logger.info("This can happen when multiple hosts share the same datasets.")
            logger.info("Marking this as non-fatal and continuing until Syncoid exits.")
            logger.info("")
            ignored_missing_destroy_snapshot = True
            continue

        elif index == PATTERN_PERMISSION_DENIED:
            die(
                child=child,
                errstr="ERROR! Incorrect password or SSH permission denied.",
                error_code=EXIT_PASSWORD_DENIED,
                logger=logger,
            )

        elif index == PATTERN_TIMEOUT:
            die(
                child,
                "ERROR! Connection timed out.",
                EXIT_CONNECTION_TIMEOUT,
                logger=logger,
            )

        elif index == PATTERN_REFUSED:
            die(
                child,
                "ERROR! Connection refused.",
                EXIT_CONNECTION_REFUSED,
                logger=logger,
            )

        elif index == PATTERN_PASSPHRASE:
            if run_context.logging_enabled:
                child.logfile = None

            if password is None:
                die(
                    child,
                    "ERROR! Password/passphrase prompt appeared, but PassWord is set to NO.",
                    EXIT_PASSWORD_DENIED,
                    logger=logger,
                )

            child.sendline(password)

            if run_context.logging_enabled:
                child.logfile = output_handle

        elif index == PATTERN_EOF:
            close_child_logfile(child, logger)
            return SyncoidAttemptResult(
                child=child,
                command=modified_command,
                repeated_pattern=repeated_pattern,
                retry_without_resume=retry_without_resume,
                ignored_missing_destroy_snapshot=ignored_missing_destroy_snapshot,
            )

        elif index == PATTERN_WARN_SKIPPING:
            die(
                child,
                "ERROR! Syncoid skipped a dataset. Check source/destination datasets.",
                EXIT_DATASET_MISSING,
                logger=logger,
            )

        elif index == PATTERN_NO_RESUME:
            retry_without_resume = True

            logger.info("")
            logger.info("----------")
            logger.info("")
            logger.info("The last transfer failed and the resume snapshot no longer exists.")
            logger.info("Gonna rerun the command with --no-resume.")
            logger.info("")

            if "--no-resume" not in syncoid_command:
                modified_command = syncoid_command + ["--no-resume"]
            else:
                modified_command = list(syncoid_command)

            logger.info("The modified command reads : %s", shlex.join(modified_command))
            logger.info("")
            logger.info("----------")
            logger.info("")

            close_child_logfile(child, logger)
            return SyncoidAttemptResult(
                child=child,
                command=modified_command,
                repeated_pattern=repeated_pattern,
                retry_without_resume=retry_without_resume,
                ignored_missing_destroy_snapshot=ignored_missing_destroy_snapshot,
            )

        elif index == PATTERN_RESUME_UNAVAILABLE:
            logger.warning("")
            logger.warning(
                "Syncoid reported that resumable receive is unavailable for this transfer."
            )
            logger.warning(
                "Syncoid explicitly continues without resume support, so Syncerate will wait for its real exit status."
            )
            logger.warning("")
            continue

        elif index == PATTERN_GENERIC_WARN:
            warning_text = safe_text(child.after) + safe_text(child.buffer)

            if (
                ignored_missing_destroy_snapshot
                and "zfs destroy" in warning_text
                and "failed: 256" in warning_text
            ):
                logger.info("")
                logger.info("Syncoid produced the known non-fatal destroy warning.")
                logger.info(
                    "Continuing because ignored_missing_destroy_snapshot is True."
                )
                logger.info("")
                continue

            die(
                child,
                "ERROR! Syncoid produced a warning.",
                EXIT_WARNING,
                logger=logger,
            )

        elif index == PATTERN_PASSWORD:
            if run_context.logging_enabled:
                child.logfile = None

            if password is None:
                die(
                    child,
                    "ERROR! Password/passphrase prompt appeared, but PassWord is set to NO.",
                    EXIT_PASSWORD_DENIED,
                    logger=logger,
                )

            child.sendline(password)

            if run_context.logging_enabled:
                child.logfile = output_handle

    close_child_logfile(child, logger)
    return SyncoidAttemptResult(
        child=child,
        command=modified_command,
        repeated_pattern=repeated_pattern,
        retry_without_resume=retry_without_resume,
        ignored_missing_destroy_snapshot=ignored_missing_destroy_snapshot,
    )


def run_replications(
    app_config: AppConfig,
    run_context: RunContext,
    dataset_pairs: list[DatasetPair],
    password: Optional[str],
    logger: logging.Logger,
) -> None:
    """Run all validated DatasetPair entries sequentially."""

    for dataset_pair in dataset_pairs:
        syncoid_execute = build_syncoid_command(
            app_config.syncoid_command,
            dataset_pair.source,
            dataset_pair.destination,
            dataset_pair.extra_arguments,
        )

        logger.info("")
        logger.info("----------")
        logger.info("")

        if dataset_pair.extra_arguments:
            logger.info("Extra Syncoid arguments for this destination:")
            logger.info("%s", list(dataset_pair.extra_arguments))
            logger.info("")

        logger.info(
            "Executing the altered Syncoid Command    :   %s",
            shlex.join(syncoid_execute),
        )
        logger.info("")

        log_command_debug(syncoid_execute, logger)

        result = ssh_command(
            syncoid_execute,
            password,
            run_context,
            logger,
        )

        if result.retry_without_resume:
            result.child.close()

            logger.info(
                "Executing the modified Syncoid Command    :    %s",
                shlex.join(result.command),
            )

            result = ssh_command(
                result.command,
                password,
                run_context,
                logger,
            )
            result.child.close()
        else:
            result.child.close()

        child = result.child

        if result.repeated_pattern:
            die(
                child,
                "ERROR: The script is repeating itself",
                EXIT_REPEATED_PATTERN,
                logger=logger,
            )

        if child.exitstatus is None and child.signalstatus is not None:
            exit_code = 128 + int(child.signalstatus)

            logger.error("")
            logger.error("Syncoid was terminated by signal: %s", child.signalstatus)
            logger.error("Using exit code: %s", exit_code)

            die(
                SynCoidFail=exit_code,
                SynCoidFailChild=child,
                logger=logger,
            )

        if child.exitstatus != EXIT_OK and result.ignored_missing_destroy_snapshot:
            logger.warning("")
            logger.warning(
                "Syncoid exited with non-zero status %s, but ignored_missing_destroy_snapshot is True.",
                child.exitstatus,
            )
            logger.warning(
                "Ignoring this because the known no-destroy-snapshot message was seen."
            )
            logger.warning("")

        if child.exitstatus != EXIT_OK and not result.ignored_missing_destroy_snapshot:
            exit_code = int(child.exitstatus)

            logger.error("")
            logger.error("This is the Syncoid exit status: %s", exit_code)

            die(
                SynCoidFail=exit_code,
                SynCoidFailChild=child,
                logger=logger,
            )


def send_error_mail(
    error: SyncerateError,
    app_config: Optional[AppConfig],
    run_context: Optional[RunContext],
    logger: logging.Logger,
) -> None:
    """Send the matching error mail without allowing mail failure to mask exit code."""

    if app_config is None or run_context is None or not app_config.mail_enabled:
        return

    try:
        if error.kind == "mqtt":
            MailTo(
                app_config,
                run_context,
                logger,
                MQTT_Fail=error.exit_code,
            )
        elif error.kind == "syncoid":
            MailTo(
                app_config,
                run_context,
                logger,
                SynCoidFail=error.exit_code,
            )
        else:
            MailTo(
                app_config,
                run_context,
                logger,
                Exit_Code=error.exit_code,
            )
    except Exception:
        logger.exception("Additionally failed to send the error mail")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Perform all startup and runtime work, returning the final exit code."""

    app_config: Optional[AppConfig] = None
    run_context: Optional[RunContext] = None
    logger: Optional[logging.Logger] = None

    try:
        args = parse_arguments(argv)
        app_config = load_app_config(args.conf)
        run_context = create_run_context(app_config)
        logger = get_logger(run_context)

        log_startup_configuration(app_config, run_context, logger)
        dataset_pairs = load_dataset_pairs(app_config, logger)
        password = resolve_password(app_config, logger)

        run_replications(
            app_config,
            run_context,
            dataset_pairs,
            password,
            logger,
        )
        successfull_run(app_config, run_context, logger)
        return EXIT_OK

    except SyncerateError as error:
        if logger is None:
            logger = get_console_logger()

        log_syncerate_error(error, logger)
        send_error_mail(error, app_config, run_context, logger)
        return error.exit_code

    except Exception:
        if logger is None:
            logger = get_console_logger()

        logger.exception("Unhandled script error")

        unexpected_error = SyncerateError(
            "Unhandled script error",
            EXIT_SCRIPT_ERROR,
            kind="script",
        )
        send_error_mail(
            unexpected_error,
            app_config,
            run_context,
            logger,
        )
        return EXIT_SCRIPT_ERROR


if __name__ == "__main__":
    sys.exit(main())
