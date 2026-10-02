"""Optional email, MQTT, and Home Assistant notification handling."""

import json
import logging
import os
import subprocess
from typing import Any, Optional

from .errors import EXIT_DATASET_MISSING, EXIT_MQTT_ERROR, EXIT_OK, SyncerateError
from .logging_setup import format_final_run_summary, format_missing_dataset_failures
from .models import AppConfig, DatasetPair, ReplicationSummary, RunContext


BROKEN_PIPE_SUCCESS_SUBJECT = "Syncerate Succsful - WARNING BROKEN PIPE"


def backup_header_text(app_config: AppConfig) -> str:
    """Return the legacy optional backup title/comment email prefix."""

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


def run_summary_header_text(
    app_config: AppConfig,
    runtime_seconds: Optional[float],
    replication_summary: Optional[ReplicationSummary] = None,
    *,
    dry_run: bool = False,
    planned_dataset_count: Optional[int] = None,
) -> str:
    """Return the shared run summary header used at the top of email bodies."""

    if runtime_seconds is None:
        return backup_header_text(app_config)

    return (
        format_final_run_summary(
            app_config,
            runtime_seconds,
            replication_summary,
            dry_run=dry_run,
            planned_dataset_count=planned_dataset_count,
        )
        + "\n\n----------\n\n"
    )


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
    BrokenPipeWarning: bool = False,
    BrokenPipeDatasets: Optional[list[DatasetPair]] = None,
    RuntimeSeconds: Optional[float] = None,
    ReplicationSummaryData: Optional[ReplicationSummary] = None,
    DryRun: bool = False,
    DryRunReportText: str = "",
    DryRunDatasetCount: Optional[int] = None,
) -> None:
    """Build and send success, warning-success, and error mail variants.

    This function does not terminate the process. The top-level main()
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

    def summary_header(
        replication_summary: Optional[ReplicationSummary] = None,
    ) -> str:
        return run_summary_header_text(
            app_config,
            RuntimeSeconds,
            replication_summary,
            dry_run=DryRun,
            planned_dataset_count=DryRunDatasetCount,
        )

    dry_run_subject_prefix = "DRY RUN - " if DryRun else ""

    if Exit_Code == EXIT_OK and DryRun:
        subject_suffix = "Attaching log" if logging_enabled else "Logs Disabled"
        subject = (
            "Successful Syncerate.py DRY RUN - No replication performed "
            f"({subject_suffix})"
        )
        body = summary_header()
        if DryRunReportText:
            body += DryRunReportText + "\n"

        attachment_files = None
        if logging_enabled and log_file is not None and os.path.isfile(log_file):
            attachment_files = [log_file]

        mail_exit_code, stderr_output = send_mail(
            subject,
            body,
            recipient,
            attachment_files,
        )
        WasMailSent(mail_exit_code, stderr_output, logger)
        return

    if Exit_Code == EXIT_OK:
        broken_pipe_datasets = BrokenPipeDatasets or []
        warning_body = ""

        if BrokenPipeWarning:
            wait_unit = (
                "second"
                if app_config.broken_pipe_retry_wait_seconds == 1
                else "seconds"
            )
            retry_unit = (
                "retry"
                if app_config.broken_pipe_retry_count == 1
                else "retries"
            )
            warning_lines = [
                BROKEN_PIPE_SUCCESS_SUBJECT,
                "",
                "Syncerate completed the dataset list successfully, but one or more datasets were skipped after exhausting their Broken Pipe retry allowance.",
            ]

            if app_config.broken_pipe_retry_count > 0:
                warning_lines.append(
                    "Each affected dataset was allowed "
                    f"{app_config.broken_pipe_retry_count} {retry_unit}, with a wait of "
                    f"{app_config.broken_pipe_retry_wait_seconds} {wait_unit} before each retry. "
                    "After the retry allowance was exhausted, that dataset was skipped and the list continued."
                )
            else:
                warning_lines.append(
                    "BrokenPipeRetryCount was set to 0, so an affected dataset was skipped immediately after the first detected Broken Pipe and the list continued."
                )

            warning_lines.append("")

            if broken_pipe_datasets:
                warning_lines.append("Skipped dataset pairs:")
                for dataset_pair in broken_pipe_datasets:
                    warning_lines.append(
                        f"- {dataset_pair.source} -> {dataset_pair.destination}"
                    )
                warning_lines.append("")

            warning_lines.extend(["----------", ""])
            warning_body = "\n".join(warning_lines)

        if logging_enabled:
            assert log_file is not None
            assert output_file is not None

            subject = (
                BROKEN_PIPE_SUCCESS_SUBJECT
                if BrokenPipeWarning
                else "Successful Syncerate.py run - No errors found (Attaching logs)"
            )
            attachment_files = [log_file, output_file]

            with open(log_file, "r", encoding="utf-8") as opened_log:
                log_contents = opened_log.read()

            body = (
                summary_header(ReplicationSummaryData)
                + warning_body
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
            subject = (
                BROKEN_PIPE_SUCCESS_SUBJECT
                if BrokenPipeWarning
                else "Successful Syncerate.py run - No errors found (Logs Disabled)"
            )
            body = (
                summary_header(ReplicationSummaryData)
                + warning_body
            )
            if not BrokenPipeWarning:
                body += subject

            mail_exit_code, stderr_output = send_mail(
                subject,
                body,
                recipient,
            )

        WasMailSent(mail_exit_code, stderr_output, logger)
        return

    if (
        Exit_Code == EXIT_DATASET_MISSING
        and ReplicationSummaryData is not None
        and ReplicationSummaryData.has_missing_dataset_failure
    ):
        subject_base = dry_run_subject_prefix + "Error running Syncerate.py - Missing ZFS dataset or pool"
        failure_text = format_missing_dataset_failures(ReplicationSummaryData)
        continuation_text = (
            "ContinueOnMissingDataset was enabled, so Syncerate continued with "
            "the remaining configured dataset pairs after each recognized missing "
            "dataset/pool error. "
            if app_config.continue_on_missing_dataset
            else
            "ContinueOnMissingDataset was disabled, so Syncerate stopped the "
            "configured dataset list after the first recognized missing dataset/pool error. "
        )
        body = (
            summary_header(ReplicationSummaryData)
            + continuation_text
            + "The run is marked failed with exit code 8 because one or more "
            + "ZFS datasets or pools were missing.\n\n"
            + "Failed dataset pairs:\n"
            + failure_text
            + "\n"
        )

        if logging_enabled:
            assert log_file is not None
            assert error_file is not None
            subject = subject_base + " (Attaching logs)"
            attachment_files = [log_file, error_file]
            if output_file is not None and os.path.isfile(output_file):
                attachment_files.append(output_file)
            mail_exit_code, stderr_output = send_mail(
                subject,
                body,
                recipient,
                attachment_files,
            )
        else:
            subject = subject_base + " (Logs Disabled)"
            mail_exit_code, stderr_output = send_mail(
                subject,
                body,
                recipient,
            )

        WasMailSent(mail_exit_code, stderr_output, logger)
        return

    if SynCoidFail is not None:
        if logging_enabled:
            assert log_file is not None
            assert error_file is not None

            subject = dry_run_subject_prefix + "Error running Syncerate.py - Syncoid error occurred (Attaching logs)"
            attachment_files = [log_file, error_file]
            if output_file is not None and os.path.isfile(output_file):
                attachment_files.append(output_file)

            body = summary_header()
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
            subject_and_body = dry_run_subject_prefix + (
                "Error running Syncerate.py - Syncoid error occurred (Logs Disabled)"
            )
            mail_exit_code, stderr_output = send_mail(
                subject_and_body,
                summary_header() + subject_and_body,
                recipient,
            )

        WasMailSent(mail_exit_code, stderr_output, logger)
        return

    if MQTT_Fail is not None:
        if logging_enabled:
            assert log_file is not None
            assert error_file is not None

            subject = dry_run_subject_prefix + "Error sending MQTT message - (Attaching logs)"
            attachment_files = [log_file, error_file]
            if output_file is not None and os.path.isfile(output_file):
                attachment_files.append(output_file)

            body = summary_header()
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
            subject_and_body = dry_run_subject_prefix + "Error sending MQTT message - (Logs Disabled)"
            mail_exit_code, stderr_output = send_mail(
                subject_and_body,
                summary_header() + subject_and_body,
                recipient,
            )

        WasMailSent(mail_exit_code, stderr_output, logger)
        return

    if Exit_Code is not None and Exit_Code != EXIT_OK:
        if logging_enabled:
            assert log_file is not None
            assert error_file is not None

            subject = dry_run_subject_prefix + "Error running Syncerate.py - This was a script error (Attaching logs)"
            attachment_files = [log_file, error_file]
            if output_file is not None and os.path.isfile(output_file):
                attachment_files.append(output_file)

            body = summary_header()
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
            subject_and_body = dry_run_subject_prefix + (
                "Error running Syncerate.py - This was a script error (Logs Disabled)"
            )
            mail_exit_code, stderr_output = send_mail(
                subject_and_body,
                summary_header() + subject_and_body,
                recipient,
            )

        WasMailSent(mail_exit_code, stderr_output, logger)

def mqtt_error_output(error: SyncerateError, max_chars: int = 4000) -> str:
    """Return the most useful bounded child/Syncoid output for MQTT failure JSON."""

    parts = [
        error.child_before,
        error.child_warning,
        error.syncoid_before,
    ]
    combined = "\n".join(part.strip() for part in parts if part and part.strip())
    if len(combined) <= max_chars:
        return combined
    return combined[-max_chars:]


def build_mqtt_status_payload(
    app_config: AppConfig,
    *,
    success: bool,
    exit_code: int,
    error_message: str = "",
    stderr_text: str = "",
    replication_summary: Optional[ReplicationSummary] = None,
    dry_run: bool = False,
    dry_run_dataset_pairs: Optional[list[DatasetPair]] = None,
) -> str:
    """Build the JSON status payload consumed by Home Assistant MQTT automations."""

    status = "success" if success else "failure"
    backup_name = app_config.backup_title or "Syncerate"
    skipped_datasets: list[dict[str, str]] = []
    failed_datasets: list[dict[str, str]] = []
    planned_datasets: list[dict[str, str]] = []
    broken_pipe_warning = False

    if dry_run_dataset_pairs:
        planned_datasets = [
            {
                "source": pair.source,
                "destination": pair.destination,
            }
            for pair in dry_run_dataset_pairs
        ]

    if replication_summary is not None:
        broken_pipe_warning = replication_summary.has_broken_pipe_warning
        skipped_datasets = [
            {
                "source": pair.source,
                "destination": pair.destination,
            }
            for pair in replication_summary.broken_pipe_failed_datasets
        ]
        failed_datasets = [
            {
                "source": failure.dataset_pair.source,
                "destination": failure.dataset_pair.destination,
                "reason": "\n".join(failure.messages),
            }
            for failure in replication_summary.missing_dataset_failures
        ]

    payload = {
        "status": status,
        "success": bool(success),
        "title": backup_name,
        "name": backup_name,
        "job": "syncerate",
        "dry_run": bool(dry_run),
        "planned_datasets": planned_datasets,
        "exit_code": int(exit_code),
        "error": error_message or "",
        "stderr": stderr_text or "",
        "warning": bool(broken_pipe_warning),
        "skipped_datasets": skipped_datasets,
        "failed_datasets": failed_datasets,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def send_mqtt_messages(
    app_config: AppConfig,
    logger: logging.Logger,
    *,
    success: bool = True,
    exit_code: int = EXIT_OK,
    error_message: str = "",
    stderr_text: str = "",
    replication_summary: Optional[ReplicationSummary] = None,
    dry_run: bool = False,
    dry_run_dataset_pairs: Optional[list[DatasetPair]] = None,
) -> None:
    """Publish real success signals, dry-run reports, or failure JSON."""

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

    broker_address = app_config.broker_address
    broker_port = app_config.broker_port
    mqtt_username = app_config.mqtt_username.strip()
    mqtt_password = app_config.mqtt_password

    auth = None
    if mqtt_username:
        auth = {
            "username": mqtt_username,
            "password": mqtt_password,
        }

    messages: list[dict[str, Any]] = []
    use_home_assistant = False
    status_topic = ""

    # Preserve the historical MQTT behavior exactly. These are success-only
    # signals: the normal mqtt_message is retained, and enabling the old Home
    # Assistant integration additionally publishes retained availability=online.
    if success and app_config.use_mqtt and not dry_run:
        use_home_assistant = app_config.use_home_assistant

        if use_home_assistant:
            messages.append(
                {
                    "topic": app_config.home_assistant_available,
                    "payload": "online",
                    "retain": True,
                    "qos": 0,
                }
            )

        messages.append(
            {
                "topic": app_config.mqtt_topic,
                "payload": app_config.mqtt_message,
                "retain": True,
                "qos": 0,
            }
        )

    # Prefer the dedicated JSON channel. Legacy-only MQTT still reports errors
    # on a separate derived topic, so success/availability consumers keep their
    # existing payloads. Neither failure path depends on the success switch.
    # Events are never retained, so reconnecting consumers do not replay them.
    if (
        app_config.mqtt_json_status
        or (not success and app_config.use_mqtt)
        or (dry_run and success and app_config.use_mqtt)
    ):
        if app_config.mqtt_json_status:
            status_topic = app_config.mqtt_json_topic.strip()
        elif dry_run and success:
            status_topic = app_config.mqtt_topic + "/dry-run"
        else:
            status_topic = app_config.mqtt_topic + "/error"
        mqtt_payload = build_mqtt_status_payload(
            app_config,
            success=success,
            exit_code=exit_code,
            error_message=error_message,
            stderr_text=stderr_text,
            replication_summary=replication_summary,
            dry_run=dry_run,
            dry_run_dataset_pairs=dry_run_dataset_pairs,
        )
        messages.append(
            {
                "topic": status_topic,
                "payload": mqtt_payload,
                "retain": False,
                "qos": 0,
            }
        )

    if not messages:
        return

    try:
        publish.multiple(
            messages,
            hostname=broker_address,
            port=broker_port,
            auth=auth,
        )
        if success and app_config.use_mqtt and not dry_run:
            logger.info(
                "Legacy MQTT success message published retained to %s",
                app_config.mqtt_topic,
            )
            if use_home_assistant:
                logger.info(
                    "Home Assistant availability message published retained to %s",
                    app_config.home_assistant_available,
                )
        if status_topic:
            logger.info(
                "MQTT JSON status published non-retained to %s: %s",
                status_topic,
                "dry-run success" if dry_run and success else ("success" if success else "failure"),
            )
    except Exception as exc:
        logger.exception("Failed publishing MQTT message(s)")
        raise SyncerateError(
            "Failed publishing MQTT message(s)",
            EXIT_MQTT_ERROR,
            kind="mqtt",
        ) from exc

def send_mqtt_failure_status(
    error: SyncerateError,
    app_config: Optional[AppConfig],
    logger: logging.Logger,
    replication_summary: Optional[ReplicationSummary] = None,
    *,
    dry_run: bool = False,
) -> None:
    """Best-effort failure JSON that never replaces the original application error."""

    if (
        app_config is None
        or not (app_config.use_mqtt or app_config.mqtt_json_status)
        or error.kind == "mqtt"
    ):
        return

    try:
        send_mqtt_messages(
            app_config,
            logger,
            success=False,
            exit_code=error.exit_code,
            error_message=error.message,
            stderr_text=mqtt_error_output(error),
            replication_summary=replication_summary,
            dry_run=dry_run,
        )
    except SyncerateError:
        logger.exception(
            "Additionally failed to publish the MQTT JSON failure status; preserving original exit code %s",
            error.exit_code,
        )

def send_error_mail(
    error: SyncerateError,
    app_config: Optional[AppConfig],
    run_context: Optional[RunContext],
    logger: logging.Logger,
    runtime_seconds: Optional[float] = None,
    replication_summary: Optional[ReplicationSummary] = None,
    *,
    dry_run: bool = False,
    dry_run_dataset_count: Optional[int] = None,
) -> None:
    """Send the matching error mail without allowing mail failure to mask exit code."""

    if app_config is None or run_context is None or not app_config.mail_enabled:
        return

    try:
        if error.kind == "dataset_missing":
            MailTo(
                app_config,
                run_context,
                logger,
                Exit_Code=error.exit_code,
                RuntimeSeconds=runtime_seconds,
                ReplicationSummaryData=replication_summary,
                DryRun=dry_run,
                DryRunDatasetCount=dry_run_dataset_count,
            )
        elif error.kind == "mqtt":
            MailTo(
                app_config,
                run_context,
                logger,
                MQTT_Fail=error.exit_code,
                RuntimeSeconds=runtime_seconds,
                DryRun=dry_run,
                DryRunDatasetCount=dry_run_dataset_count,
            )
        elif error.kind == "syncoid":
            MailTo(
                app_config,
                run_context,
                logger,
                SynCoidFail=error.exit_code,
                RuntimeSeconds=runtime_seconds,
                DryRun=dry_run,
                DryRunDatasetCount=dry_run_dataset_count,
            )
        else:
            MailTo(
                app_config,
                run_context,
                logger,
                Exit_Code=error.exit_code,
                RuntimeSeconds=runtime_seconds,
                DryRun=dry_run,
                DryRunDatasetCount=dry_run_dataset_count,
            )
    except Exception:
        logger.exception("Additionally failed to send the error mail")
