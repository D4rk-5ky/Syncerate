"""Offline regression checks: external commands are mocked, never executed."""
import argparse
from contextlib import contextmanager
import datetime as dt
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location('snap_app', ROOT / 'SnapBeforeWatchTower.py')
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


@contextmanager
def temporary_directory():
    """Use ordinary directory permissions for portable sandbox test files."""
    folder = Path(tempfile.gettempdir()).resolve() / ('snap-test-' + uuid.uuid4().hex)
    folder.mkdir(mode=0o755)
    try:
        yield str(folder)
    finally:
        for child in folder.iterdir():
            if child.is_dir():
                for nested in child.iterdir():
                    nested.unlink()
                child.rmdir()
            else:
                child.unlink()
        folder.rmdir()


def write_config(folder, *, command='create', dataset_file='datasets.txt', older_than='7d', retain_count=10,
                 dry_run=False, mail='', mqtt=''):
    """Write a minimal TOML config used by parser/integration tests."""
    path = Path(folder) / 'config.toml'
    path.write_text(
        '[application]\n'
        f'command = "{command}"\n'
        f'dataset_file = "{dataset_file}"\n'
        f'older_than = "{older_than}"\n'
        f'retain_count = {retain_count}\n'
        f'dry_run = {str(dry_run).lower()}\n'
        f'{mail}'
        f'{mqtt}',
        encoding='utf-8',
    )
    return path


class BehaviorTests(unittest.TestCase):
    """Exercise existing safety boundaries with disposable files and mocked processes."""

    def setUp(self):
        self.log = Mock()
        self.err = Mock()

    def test_duration_units_and_invalid_input(self):
        for value, days in [('7d', 7), ('2w', 14), ('1m', 30), ('0d', 0)]:
            self.assertEqual(app.parse_older_than(value), dt.timedelta(days=days))
        for value in ['-1d', '1.5d', '7D', '7', 'garbage']:
            with self.assertRaises(argparse.ArgumentTypeError):
                app.parse_older_than(value)

    def test_toml_config_maps_former_flags_and_resolves_relative_dataset(self):
        with temporary_directory() as folder:
            config = write_config(
                folder,
                mail='\n[mail]\nenabled = true\nrecipient = "test@example.com"\non_success = true\n',
                mqtt='\n[mqtt]\nenabled = true\nhost = "broker"\ntopic = "test/status"\nusername = "user"\npassword = "secret"\n',
                dry_run=True,
            )
            args, mqtt_config = app.load_app_config(config)
        self.assertEqual(args.command, 'create')
        self.assertEqual(args.file, str((Path(folder) / 'datasets.txt').resolve()))
        self.assertEqual(args.older_than, dt.timedelta(days=7))
        self.assertEqual(args.retain_count, 10)
        self.assertTrue(args.dry_run)
        self.assertEqual(args.send_mail, 'test@example.com')
        self.assertTrue(args.mail_on_success)
        self.assertEqual(mqtt_config['password'], 'secret')

    def test_toml_optional_sections_default_disabled(self):
        with temporary_directory() as folder:
            config = write_config(folder)
            args, mqtt_config = app.load_app_config(config)
        self.assertIsNone(args.send_mail)
        self.assertFalse(args.mail_on_success)
        self.assertIsNone(mqtt_config)

    def test_toml_invalid_values_and_old_flag_keys_are_rejected(self):
        invalid_documents = [
            '[application]\ncommand="bad"\ndataset_file="datasets"\nolder_than="7d"\nretain_count=10\ndry_run=true\n',
            '[application]\ncommand="create"\ndataset_file="datasets"\nolder_than="bad"\nretain_count=10\ndry_run=true\n',
            '[application]\ncommand="create"\ndataset_file="datasets"\nolder_than="7d"\nretain_count=true\ndry_run=true\n',
            '[application]\ncommand="create"\ndataset_file="datasets"\nolder_than="7d"\nretain_count=10\ndry_run="true"\n',
            '[application]\ncommand="create"\ndataset_file="datasets"\nolder_than="7d"\nretain_count=10\ndry_run=true\nfile="old-flag"\n',
            '[application]\ncommand="create"\ndataset_file="datasets"\nolder_than="7d"\nretain_count=10\ndry_run=true\n\n[mail]\nenabled=true\nrecipient=""\non_success=false\n',
            '[application]\ncommand="create"\ndataset_file="datasets"\nolder_than="7d"\nretain_count=10\ndry_run=true\n\n[mqtt]\nenabled=false\npassword_env="OLD"\n',
            '[unknown]\nvalue=1\n',
        ]
        with temporary_directory() as folder:
            path = Path(folder) / 'bad.toml'
            for text in invalid_documents:
                path.write_text(text, encoding='utf-8')
                with self.subTest(text=text), self.assertRaises(ValueError):
                    app.load_app_config(path)

    def test_retention_preserves_newest_and_ignores_unmanaged_or_invalid_dates(self):
        names = [
            'tank/data@SnapBeforeWatchTower-Date-2000-01-01_00_00_00',
            'tank/data@SnapBeforeWatchTower-Date2001-01-01_00_00_00',
            'tank/data@SnapBeforeWatchTower-Date-2002-01-01_00_00_00',
            'tank/data@manual-2000-01-01_00_00_00',
            'tank/data@SnapBeforeWatchTower-Date-2000-99-01_00_00_00',
            'tank/data@SnapBeforeWatchTower-Date-2000-01-01_00_00_00-extra',
        ]
        with patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '\n'.join(names), '')) as run:
            app.delete_old_snapshots(self.log, self.err, 'tank/data', dt.timedelta(days=7), 1)
        commands = [c.args[0] for c in run.call_args_list]
        self.assertEqual(commands[0], ['zfs', 'list', '-H', '-t', 'snapshot', '-o', 'name', 'tank/data'])
        self.assertEqual(commands[1:], [['zfs', 'destroy', names[1]], ['zfs', 'destroy', names[0]]])

    def test_retention_preserves_recent_snapshot_without_count_floor(self):
        future = 'tank/data@SnapBeforeWatchTower-Date-2999-01-01_00_00_00'
        with patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, future, '')) as run:
            app.delete_old_snapshots(self.log, self.err, 'tank/data', dt.timedelta(days=7), 0)
        self.assertEqual(run.call_count, 1)

    def test_nonpositive_count_disables_floor(self):
        name = 'tank/data@SnapBeforeWatchTower-Date-2000-01-01_00_00_00'
        for count in [0, -1]:
            with patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, name, '')) as run:
                app.delete_old_snapshots(self.log, self.err, 'tank/data', dt.timedelta(days=7), count)
            self.assertEqual(run.call_args.args[0], ['zfs', 'destroy', name])

    def test_dry_run_lists_but_never_creates_destroys_or_captures_docker(self):
        name = 'tank/data@SnapBeforeWatchTower-Date-2000-01-01_00_00_00'
        with patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, name, '')) as run:
            app.create_snapshot(self.log, self.err, 'tank/data', dry_run=True)
            self.assertIsNone(app.save_docker_image_digests(self.log, self.err, 'unused', 'unused', dry_run=True))
            app.delete_old_snapshots(self.log, self.err, 'tank/data', dt.timedelta(days=7), 0, dry_run=True)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][:2], ['zfs', 'list'])

    def test_list_failure_prevents_destroy(self):
        with patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'list failed')) as run:
            with self.assertRaises(app.CommandError):
                app.delete_old_snapshots(self.log, self.err, 'tank/data', dt.timedelta(days=7), 1)
        self.assertEqual(run.call_count, 1)

    def test_create_failure_propagates(self):
        with patch.object(app.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['zfs'], stderr='failed')):
            with self.assertRaises(subprocess.CalledProcessError):
                app.create_snapshot(self.log, self.err, 'tank/data')

    def test_missing_dataset_detection_only_accepts_missing_zfs_messages(self):
        missing = subprocess.CalledProcessError(1, ['zfs'], stderr="cannot open 'tank/missing': dataset does not exist")
        alternate = app.CommandError(['zfs', 'list'], 1, '', "cannot open 'tank/missing': no such pool or dataset")
        unrelated = app.CommandError(['zfs', 'list'], 1, '', "cannot open 'tank/data': permission denied")
        self.assertTrue(app.is_missing_dataset_error(missing))
        self.assertTrue(app.is_missing_dataset_error(alternate))
        self.assertFalse(app.is_missing_dataset_error(unrelated))

    def test_create_continues_after_missing_dataset_then_fails_run_and_sends_failure_mail(self):
        with temporary_directory() as folder:
            dataset_file = Path(folder) / 'datasets.txt'
            dataset_file.write_text('tank/missing\ntank/good\n', encoding='utf-8')
            args = argparse.Namespace(
                command='create', file=str(dataset_file), older_than=dt.timedelta(days=7), retain_count=1,
                send_mail='test@example.com', mail_on_success=True, dry_run=False,
            )
            reporter = Mock()
            missing = subprocess.CalledProcessError(
                1, ['zfs', 'snapshot'], stderr="cannot open 'tank/missing': dataset does not exist"
            )
            create = Mock(side_effect=[missing, None])
            retention = Mock()
            cleanup = Mock()
            mail = Mock()
            err_path = str(Path(folder) / 'run.err')
            with patch.object(app.os, 'geteuid', return_value=0, create=True), \
                 patch.object(app, 'pick_log_folder', return_value=folder), \
                 patch.object(app, 'setup_logger', return_value=(self.log, self.err, err_path)), \
                 patch.object(app, 'save_docker_image_digests'), \
                 patch.object(app, 'create_snapshot', create), \
                 patch.object(app, 'delete_old_snapshots', retention), \
                 patch.object(app, 'delete_old_files', cleanup), \
                 patch.object(app, 'MailTo', mail):
                with self.assertRaises(app.MissingDatasetsError) as failure:
                    app.run(args, reporter)

        self.assertIn('dataset does not exist', str(failure.exception))
        self.assertIn('tank/missing', str(failure.exception))
        self.assertEqual([call.args[2] for call in create.call_args_list], ['tank/missing', 'tank/good'])
        retention.assert_called_once()
        self.assertEqual(retention.call_args.args[2], 'tank/good')
        cleanup.assert_called_once()
        mail.assert_called_once()
        self.assertEqual(mail.call_args.kwargs['subject'], 'SnapBeforeWatchTower FAILED - missing dataset')
        self.assertIn('tank/missing', mail.call_args.kwargs['intro'])

    def test_delete_continues_after_missing_dataset_and_processes_following_dataset(self):
        with temporary_directory() as folder:
            dataset_file = Path(folder) / 'datasets.txt'
            dataset_file.write_text('tank/missing\ntank/good\n', encoding='utf-8')
            args = argparse.Namespace(
                command='delete', file=str(dataset_file), older_than=dt.timedelta(days=7), retain_count=1,
                send_mail=None, mail_on_success=False, dry_run=False,
            )
            reporter = Mock()
            missing = app.CommandError(
                ['zfs', 'list', 'tank/missing'], 1, '', "cannot open 'tank/missing': dataset does not exist"
            )
            retention = Mock(side_effect=[missing, None])
            cleanup = Mock()
            err_path = str(Path(folder) / 'run.err')
            with patch.object(app.os, 'geteuid', return_value=0, create=True), \
                 patch.object(app, 'pick_log_folder', return_value=folder), \
                 patch.object(app, 'setup_logger', return_value=(self.log, self.err, err_path)), \
                 patch.object(app, 'delete_old_snapshots', retention), \
                 patch.object(app, 'delete_old_files', cleanup):
                with self.assertRaises(app.MissingDatasetsError):
                    app.run(args, reporter)

        self.assertEqual([call.args[2] for call in retention.call_args_list], ['tank/missing', 'tank/good'])
        cleanup.assert_called_once()

    def test_unrelated_dataset_command_error_still_aborts_immediately(self):
        with temporary_directory() as folder:
            dataset_file = Path(folder) / 'datasets.txt'
            dataset_file.write_text('tank/denied\ntank/good\n', encoding='utf-8')
            args = argparse.Namespace(
                command='create', file=str(dataset_file), older_than=dt.timedelta(days=7), retain_count=1,
                send_mail=None, mail_on_success=False, dry_run=False,
            )
            reporter = Mock()
            denied = subprocess.CalledProcessError(1, ['zfs', 'snapshot'], stderr='permission denied')
            create = Mock(side_effect=denied)
            cleanup = Mock()
            err_path = str(Path(folder) / 'run.err')
            with patch.object(app.os, 'geteuid', return_value=0, create=True), \
                 patch.object(app, 'pick_log_folder', return_value=folder), \
                 patch.object(app, 'setup_logger', return_value=(self.log, self.err, err_path)), \
                 patch.object(app, 'save_docker_image_digests'), \
                 patch.object(app, 'create_snapshot', create), \
                 patch.object(app, 'delete_old_snapshots'), \
                 patch.object(app, 'delete_old_files', cleanup):
                with self.assertRaises(subprocess.CalledProcessError):
                    app.run(args, reporter)

        self.assertEqual(create.call_count, 1)
        cleanup.assert_not_called()

    def test_log_groups_count_age_and_dry_run(self):
        with temporary_directory() as folder:
            base = Path(folder)
            for year in [2000, 2001]:
                for extension in ['log', 'err', 'digest']:
                    (base / f'SnapBeforeWatchTower-Date-{year}-01-01_00_00_00.{extension}').write_text('test')
            (base / 'unrelated.txt').write_text('keep')
            app.delete_old_files(self.log, self.err, folder, dt.timedelta(days=7), 1, dry_run=True)
            self.assertEqual(len(list(base.iterdir())), 7)
            app.delete_old_files(self.log, self.err, folder, dt.timedelta(days=7), 1)
            self.assertEqual(len(list(base.iterdir())), 4)
            self.assertTrue(all('2001' in p.name or p.name == 'unrelated.txt' for p in base.iterdir()))
            app.delete_old_files(self.log, self.err, folder, dt.timedelta(days=7), 0)
            self.assertEqual([p.name for p in base.iterdir()], ['unrelated.txt'])

    def test_docker_nonzero_is_logged_and_returns_none(self):
        with temporary_directory() as folder:
            with patch.object(app.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'docker failed')):
                self.assertIsNone(app.save_docker_image_digests(self.log, self.err, folder, 'test'))
            self.assertEqual(list(Path(folder).iterdir()), [])
            self.err.error.assert_called()

    def test_nonroot_refuses_before_dataset_or_external_commands(self):
        with temporary_directory() as folder:
            config = write_config(folder, dataset_file='does-not-exist', dry_run=True)
            with patch.object(sys, 'argv', ['app', '-c', str(config)]), \
                 patch.object(app.os, 'geteuid', return_value=1000, create=True), \
                 patch.object(app, 'pick_log_folder', return_value='mock-logs'), \
                 patch.object(app, 'setup_logger', return_value=(self.log, self.err, 'unused.err')), \
                 patch.object(app.subprocess, 'run') as run, patch.object(app.subprocess, 'Popen') as popen:
                with self.assertRaises(SystemExit) as failure:
                    app.main()
        self.assertEqual(failure.exception.code, 1)
        run.assert_not_called()
        popen.assert_not_called()

    def test_main_create_order_and_docker_failure_continuation(self):
        with temporary_directory() as folder:
            datasets = Path(folder) / 'datasets.txt'
            datasets.write_text('tank/data\n\n tank/other \n')
            config = write_config(folder)
            events = Mock()
            events.capture.return_value = None
            with patch.object(sys, 'argv', ['app', '-c', str(config)]), \
                 patch.object(app.os, 'geteuid', return_value=0, create=True), \
                 patch.object(app, 'pick_log_folder', return_value=folder), \
                 patch.object(app, 'setup_logger', return_value=(self.log, self.err, str(Path(folder) / 'unused.err'))), \
                 patch.object(app, 'save_docker_image_digests', events.capture), \
                 patch.object(app, 'create_snapshot', events.create), \
                 patch.object(app, 'delete_old_snapshots', events.retention), \
                 patch.object(app, 'delete_old_files', events.cleanup):
                app.main()
            self.assertEqual([c[0] for c in events.mock_calls], ['capture', 'create', 'retention', 'create', 'retention', 'cleanup'])
            self.assertEqual([c.args[2] for c in events.create.call_args_list], ['tank/data', 'tank/other'])

    def test_mail_options_precede_recipient(self):
        proc = Mock(returncode=0)
        proc.communicate.return_value = (None, b'')
        with patch.object(app.subprocess, 'Popen', return_value=proc) as popen:
            self.assertEqual(app.send_mail('Report', 'Body', 'test@example.com', ['run.log']), (0, ''))
        self.assertEqual(popen.call_args.args[0], ['mail', '-s', 'Report', '--attach', 'run.log', 'test@example.com'])


class CLITests(unittest.TestCase):
    """Verify that -c CONFIG is the only public command-line option."""

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(ROOT / 'SnapBeforeWatchTower.py'), *args], capture_output=True, text=True)

    def test_only_config_flag_is_accepted(self):
        for args in [[], ['-h'], ['--version'], ['--config', 'x.toml'], ['-f', 'datasets'], ['-c', 'x.toml', '--dry-run']]:
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 2, (args, result.stdout, result.stderr))
            self.assertNotIn('Traceback', result.stderr)
        missing = self.run_cli('-c', 'does-not-exist.toml')
        self.assertEqual(missing.returncode, 2)
        self.assertIn('Cannot load configuration', missing.stderr)
        self.assertIn('-c CONFIG', missing.stderr)


if __name__ == '__main__':
    unittest.main()
