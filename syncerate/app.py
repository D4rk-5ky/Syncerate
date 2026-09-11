"""Top-level application orchestration and final error boundary."""

import configparser
import logging
import time
from typing import Optional, Sequence

from .cli import parse_arguments
from .config import load_app_config
from .datasets import load_dataset_pairs
from .errors import EXIT_OK, EXIT_SCRIPT_ERROR, SyncerateError
from .logging_setup import (
    create_run_context,
    get_console_logger,
    get_logger,
    log_startup_configuration,
    log_final_run_summary,
)
from .models import AppConfig, ReplicationSummary, RunContext
from .notifications import (
    MailTo,
    send_error_mail,
    send_mqtt_failure_status,
    send_mqtt_messages,
)
from .syncoid_runner import private_ssh_agent, resolve_password, run_replications
from .system_actions import SystemAction


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
        if error.message:
            logger.error("%s", error.message)
        logger.error("Exit code: %s", error.exit_code)

    logger.error("")
    logger.error("----------")
    logger.error("")


def successfull_run(
    app_config: AppConfig,
    run_context: RunContext,
    logger: logging.Logger,
    replication_summary: Optional[ReplicationSummary] = None,
    runtime_seconds: Optional[float] = None,
) -> None:
    """Run success-stage notifications and the optional system action."""

    if replication_summary is None:
        replication_summary = ReplicationSummary()

    logger.info("")
    logger.info("----------")
    logger.info("")
    if replication_summary.has_broken_pipe_warning:
        logger.warning("The Script ended successfully with Broken Pipe warnings")
        logger.warning(
            "%s dataset(s) were skipped after exhausting %s configured Broken Pipe retries per dataset.",
            len(replication_summary.broken_pipe_failed_datasets),
            app_config.broken_pipe_retry_count,
        )
        for dataset_pair in replication_summary.broken_pipe_failed_datasets:
            logger.warning(
                "Skipped after Broken Pipe retry limit: %s -> %s",
                dataset_pair.source,
                dataset_pair.destination,
            )
    else:
        logger.info("The Script ended successfully")
    logger.info("")
    logger.info(
        "Now going over MAIL, MQTT and System Option, if option is set in the .cfg file"
    )
    logger.info("")
    logger.info(
        "MQTT failures can still be fatal here; mail and system-action failures are logged as best-effort post-run actions"
    )
    logger.info("")

    if run_context.logging_enabled:
        assert run_context.output_file is not None
        with open(run_context.output_file, "a", encoding="utf-8") as output_file:
            lines_of_text = [
                "",
                "----------",
                "",
                (
                    "The Script ended successfully with Broken Pipe warnings"
                    if replication_summary.has_broken_pipe_warning
                    else "The Script ended successfully"
                ),
                "",
            ]

            if replication_summary.has_broken_pipe_warning:
                lines_of_text.append(
                    f"{len(replication_summary.broken_pipe_failed_datasets)} dataset(s) were skipped after exhausting {app_config.broken_pipe_retry_count} configured Broken Pipe retries per dataset."
                )
                for dataset_pair in replication_summary.broken_pipe_failed_datasets:
                    lines_of_text.append(
                        "Skipped after Broken Pipe retry limit: "
                        f"{dataset_pair.source} -> {dataset_pair.destination}"
                    )
                lines_of_text.append("")

            lines_of_text.extend(
                [
                    "Now going over MAIL, MQTT and System Option, if option is set in the .cfg file",
                    "",
                    "MQTT failures can still be fatal here; mail and system-action failures are logged as best-effort post-run actions",
                    "",
                    "----------",
                    "",
                ]
            )

            for line in lines_of_text:
                output_file.write(line + "\n")

    if app_config.use_mqtt or app_config.mqtt_json_status:
        send_mqtt_messages(
            app_config,
            logger,
            success=True,
            exit_code=EXIT_OK,
            replication_summary=replication_summary,
        )

    if runtime_seconds is not None:
        log_final_run_summary(app_config, runtime_seconds, logger)

    if app_config.mail_enabled:
        try:
            MailTo(
                app_config,
                run_context,
                logger,
                Exit_Code=EXIT_OK,
                BrokenPipeWarning=replication_summary.has_broken_pipe_warning,
                BrokenPipeDatasets=replication_summary.broken_pipe_failed_datasets,
                RuntimeSeconds=runtime_seconds,
            )
        except Exception:
            logger.exception(
                "Failed sending the success email; continuing because mail delivery "
                "is a best-effort notification and replication already completed."
            )

    if app_config.system_action_enabled:
        SystemAction(app_config, logger)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Perform all startup and runtime work, returning the final exit code."""

    app_config: Optional[AppConfig] = None
    run_context: Optional[RunContext] = None
    logger: Optional[logging.Logger] = None
    started_at = time.monotonic()

    try:
        args = parse_arguments(argv)
        try:
            app_config = load_app_config(args.conf)
        except (OSError, configparser.Error, ValueError) as exc:
            raise SyncerateError(
                f"Configuration error: {exc}",
                EXIT_SCRIPT_ERROR,
                kind="script",
            ) from exc

        run_context = create_run_context(app_config)
        logger = get_logger(run_context)

        log_startup_configuration(app_config, run_context, logger)
        dataset_pairs = load_dataset_pairs(app_config, logger)
        password = resolve_password(app_config, logger)

        with private_ssh_agent(app_config, password, logger) as ssh_agent_session:
            replication_summary = run_replications(
                app_config,
                run_context,
                dataset_pairs,
                password,
                logger,
                ssh_agent_session=ssh_agent_session,
            )
        runtime_seconds = time.monotonic() - started_at
        successfull_run(
            app_config,
            run_context,
            logger,
            replication_summary,
            runtime_seconds=runtime_seconds,
        )
        return EXIT_OK

    except SyncerateError as error:
        if logger is None:
            logger = get_console_logger()

        log_syncerate_error(error, logger)
        runtime_seconds = time.monotonic() - started_at
        log_final_run_summary(app_config, runtime_seconds, logger)
        send_mqtt_failure_status(error, app_config, logger)
        send_error_mail(
            error,
            app_config,
            run_context,
            logger,
            runtime_seconds=runtime_seconds,
        )
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
        runtime_seconds = time.monotonic() - started_at
        log_final_run_summary(app_config, runtime_seconds, logger)
        send_mqtt_failure_status(unexpected_error, app_config, logger)
        send_error_mail(
            unexpected_error,
            app_config,
            run_context,
            logger,
            runtime_seconds=runtime_seconds,
        )
        return EXIT_SCRIPT_ERROR
