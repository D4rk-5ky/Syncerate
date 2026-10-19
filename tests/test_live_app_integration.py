"""Verify opt-in monitor follows the original lock and error boundaries."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from syncerate.app import main
from syncerate.errors import EXIT_BACKUP_LOCKED, SyncerateError
from syncerate.models import ReplicationSummary
from tests.helpers import make_config


class LiveAppIntegrationTests(unittest.TestCase):
    def _files(self, root):
        config = root / 'job.toml'
        config.write_text('', encoding='utf-8')
        src = root / 'source-list'
        dst = root / 'dest-list'
        src.write_text('pool/a\n', encoding='utf-8')
        dst.write_text('backup/a\n', encoding='utf-8')
        return config, src, dst

    def test_monitor_instantiated_after_lock_only_and_finished_on_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            config, src, dst = self._files(Path(td))
            cfg = make_config(config_path=str(config), source_list_path=str(src),
                              destination_list_path=str(dst), live_mqtt_enabled=True)
            with (mock.patch('syncerate.app.load_app_config', return_value=cfg),
                  mock.patch('syncerate.app.LiveBackupMonitor') as monitor,
                  contextlib.redirect_stdout(io.StringIO())):
                result = main(['-c', str(config), '--dry-run'])
            self.assertEqual(result, 0)
            monitor.assert_called_once()
            monitor.return_value.start.assert_called_once()
            monitor.return_value.planned.assert_called_once_with(1)
            self.assertEqual(monitor.return_value.finish.call_args.args[:2], ('success', 0))
            monitor.return_value.stop.assert_called_once()

    def test_failed_preflight_produces_live_failed_result_but_never_replicates(self):
        with tempfile.TemporaryDirectory() as td:
            config, src, dst = self._files(Path(td))
            dst.write_text('backup/DIFFERENT\n', encoding='utf-8')
            cfg = make_config(config_path=str(config), source_list_path=str(src),
                              destination_list_path=str(dst), live_mqtt_enabled=True)
            with (mock.patch('syncerate.app.load_app_config', return_value=cfg),
                  mock.patch('syncerate.app.LiveBackupMonitor') as monitor,
                  mock.patch('syncerate.app.run_replications') as replicate,
                  contextlib.redirect_stdout(io.StringIO())):
                code = main(['-c', str(config)])
            self.assertEqual(code, 1)
            replicate.assert_not_called()
            self.assertEqual(monitor.return_value.finish.call_args.args[:2], ('failed', 1))
            monitor.return_value.stop.assert_called_once()

    def test_live_progress_callback_flows_into_runner_without_changing_legacy_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            config, src, dst = self._files(Path(td))
            cfg = make_config(config_path=str(config), source_list_path=str(src),
                              destination_list_path=str(dst), live_mqtt_enabled=True)
            summary = ReplicationSummary(total_datasets=1, attempted_datasets=1, completed_datasets=1)
            with (mock.patch('syncerate.app.load_app_config', return_value=cfg),
                  mock.patch('syncerate.app.LiveBackupMonitor') as monitor,
                  mock.patch('syncerate.app.private_ssh_agent') as ssh_agent,
                  mock.patch('syncerate.app.run_replications', return_value=summary) as runner,
                  mock.patch('syncerate.app.successfull_run') as completed,
                  contextlib.redirect_stdout(io.StringIO())):
                ssh_agent.return_value.__enter__.return_value = None
                result = main(['-c', str(config)])
            self.assertEqual(result, 0)
            runner.assert_called_once()
            self.assertIs(runner.call_args.kwargs['progress_callback'], monitor.return_value.progress)
            completed.assert_called_once()
            self.assertEqual(monitor.return_value.finish.call_args.args[:2], ('success', 0))

    def test_duplicate_start_never_creates_status_monitor_or_releases_owner(self):
        with tempfile.TemporaryDirectory() as td:
            config, src, dst = self._files(Path(td))
            cfg = make_config(config_path=str(config), source_list_path=str(src),
                              destination_list_path=str(dst), live_mqtt_enabled=True)
            with (mock.patch('syncerate.app.load_app_config', return_value=cfg),
                  mock.patch('syncerate.app.BackupLock.acquire',
                             side_effect=SyncerateError('Already locked', EXIT_BACKUP_LOCKED, kind='locked')),
                  mock.patch('syncerate.app.LiveBackupMonitor') as monitor,
                  mock.patch('syncerate.app.publish_duplicate_event') as duplicate_event,
                  contextlib.redirect_stdout(io.StringIO())):
                code = main(['-c', str(config)])
            self.assertEqual(code, EXIT_BACKUP_LOCKED)
            monitor.assert_not_called()
            duplicate_event.assert_called_once()
            self.assertEqual(duplicate_event.call_args.kwargs['exit_code'], EXIT_BACKUP_LOCKED)


if __name__ == '__main__':
    unittest.main()
