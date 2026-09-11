import logging
import unittest
from unittest import mock

from syncerate.system_actions import SystemAction
from tests.helpers import make_config


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class SystemActionTests(unittest.TestCase):
    def setUp(self):
        self.handler = ListHandler()
        self.logger = logging.getLogger(f"system-action-{id(self)}")
        self.logger.handlers = [self.handler]
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

    @mock.patch("syncerate.system_actions.subprocess.run")
    def test_disabled_action_returns_without_running_shell(self, run):
        SystemAction(make_config(system_option="No"), self.logger)
        run.assert_not_called()

    @mock.patch("syncerate.system_actions.subprocess.run")
    def test_nonzero_action_is_logged_but_does_not_raise(self, run):
        run.return_value.returncode = 17
        SystemAction(make_config(system_option="false"), self.logger)
        run.assert_called_once_with("false", shell=True, check=False)
        self.assertTrue(any("non-zero status 17" in m for m in self.handler.messages))

    @mock.patch("syncerate.system_actions.time.sleep")
    @mock.patch("syncerate.system_actions.subprocess.run")
    def test_mail_enabled_preserves_two_minute_delay(self, run, sleep):
        run.return_value.returncode = 0
        SystemAction(
            make_config(system_option="echo done", mail_option="user@example.test"),
            self.logger,
        )
        sleep.assert_called_once_with(120)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
