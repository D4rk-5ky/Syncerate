"""Successful-run system command handling."""

import logging
import subprocess
import time

from .models import AppConfig


def SystemAction(app_config: AppConfig, logger: logging.Logger) -> None:
    """Run the configured successful-run shell command and log its result."""

    if not app_config.system_action_enabled:
        return

    logger.info("")
    logger.info("----------")
    logger.info("")
    logger.info("The system has an option after the script finishes")
    logger.info("")
    logger.info("The option is")
    logger.info("")
    logger.info("%s", app_config.system_option)
    logger.info("")

    if app_config.mail_enabled:
        logger.info("Gonna sleep for 2 minutes to insure mail is sent")
        logger.info("")
        logger.info("Then execute the command\t:\t%s", app_config.system_option)
        logger.info("")
        logger.info("----------")
        time.sleep(120)
    else:
        logger.info("No mail option chosen")
        logger.info("")
        logger.info("Gonna execute the command\t:\t%s", app_config.system_option)
        logger.info("")
        logger.info("----------")

    try:
        result = subprocess.run(app_config.system_option, shell=True, check=False)
    except Exception:
        logger.exception("Failed running SystemAction")
        return

    if result.returncode != 0:
        logger.error(
            "SystemAction exited with non-zero status %s; preserving the completed "
            "Syncerate run exit behavior.",
            result.returncode,
        )
    else:
        logger.info("SystemAction completed successfully")
