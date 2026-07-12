"""Optional email, MQTT, and Home Assistant notification handling."""

import logging
import os
import subprocess
from typing import Any, Optional

from .config import CONFIG_SECTION, option_is_enabled
from .errors import EXIT_MQTT_ERROR, EXIT_OK, SyncerateError
from .models import AppConfig, RunContext


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
