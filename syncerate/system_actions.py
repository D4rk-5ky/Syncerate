"""Successful-run system command handling."""

import logging
import subprocess
import time

from .models import AppConfig


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
