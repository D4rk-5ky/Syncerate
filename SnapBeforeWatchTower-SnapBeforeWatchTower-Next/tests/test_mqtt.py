"""MQTT contract and lifecycle tests; no broker, Paho installation, or network needed."""
import io
import json
import logging
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import Mock, patch

from test_app import app, temporary_directory
import mqtt_report as mqtt


class MQTTTests(unittest.TestCase):
    """Verify TOML-sourced MQTT validation, non-retained publishing, and safe run integration."""

    def setUp(self):
        self.config = dict(mqtt.DEFAULTS, host='broker.example', topic='test/snap/status')

    def validate(self, value, dry_run=True, enabled=True):
        with temporary_directory() as folder:
            return mqtt.validate_config(value, Path(folder), dry_run=dry_run, enabled=enabled)

    def test_config_defaults_tls_port_and_disabled_mode(self):
        result = self.validate({'host': 'broker', 'topic': 'test/status'})
        self.assertEqual(result, dict(mqtt.DEFAULTS, host='broker', topic='test/status'))
        result = self.validate({'host': 'broker', 'topic': 'test/status', 'tls': True})
        self.assertEqual(result['port'], 8883)
        self.assertIsNone(self.validate({}, enabled=False))

    def test_invalid_config_stops_early(self):
        for update in [
            {'topic': 'a/#'}, {'port': True}, {'qos': 3}, {'timeout': 0}, {'timeout': 121},
            {'tls': 'false'}, {'retain': True}, {'username': 12}, {'password_env': 'TEST_PASSWORD'},
            {'password': 12}, {'cert_file': 'a.pem'}, {'ca_file': 'a.pem'}, {'topic': ''}, {'host': ''},
        ]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                value = dict(host='broker', topic='test/status')
                value.update(update)
                self.validate(value)
        with self.assertRaises(ValueError):
            self.validate([])
        with self.assertRaisesRegex(ValueError, 'unsupported key'):
            self.validate({'password_env': 'OLD_ENV_NAME'}, enabled=False)

    def test_password_optional_strings_and_dependency_validation(self):
        value = dict(self.config, username='user', password='plain-secret')
        self.assertEqual(self.validate(value)['password'], 'plain-secret')
        anonymous = self.validate(dict(self.config, username='', password='', ca_file='', cert_file='', key_file=''))
        self.assertIsNone(anonymous['username'])
        self.assertIsNone(anonymous['password'])
        with self.assertRaisesRegex(ValueError, 'password requires username'):
            self.validate(dict(self.config, password='plain-secret'))
        with patch.object(mqtt.importlib, 'import_module', side_effect=ImportError('missing')):
            with self.assertRaisesRegex(ValueError, 'requirements-mqtt.txt'):
                self.validate(self.config, dry_run=False)

    def test_tls_relative_paths_resolve_from_toml_directory(self):
        with temporary_directory() as folder:
            base = Path(folder)
            for name in ['ca.pem', 'client.pem', 'client.key']:
                (base / name).write_text('test', encoding='utf-8')
            result = mqtt.validate_config(
                dict(self.config, tls=True, ca_file='ca.pem', cert_file='client.pem', key_file='client.key'),
                base,
                dry_run=True,
            )
            self.assertEqual(result['ca_file'], str((base / 'ca.pem').resolve()))
            self.assertEqual(result['cert_file'], str((base / 'client.pem').resolve()))
            self.assertEqual(result['key_file'], str((base / 'client.key').resolve()))

    def test_payload_success_warning_and_failure_contract(self):
        for exc, errors, status, code, warning in [
            (None, '', 'success', 0, False),
            (None, 'Digest collection failed', 'success', 0, True),
            (RuntimeError('Snapshot failed'), 'zfs failure', 'failure', 1, False),
            (SystemExit(1), 'Must run as root', 'failure', 1, False),
            (KeyboardInterrupt(), '', 'failure', 130, False),
        ]:
            payload = mqtt.build_payload(self.config, 'create', '0.0.6', exc, errors, 'run-123')
            self.assertEqual((payload['status'], payload['exit_code'], payload['warning']), (status, code, warning))
            for key in ['title', 'name', 'job', 'error', 'stderr', 'run_id', 'finished_at']:
                self.assertIsInstance(payload[key], str)
            self.assertEqual(json.loads(json.dumps(payload)), payload)
            self.assertEqual(payload['title'], self.config['title'])
            if status == 'failure':
                self.assertTrue(payload['error'])

    def test_missing_dataset_failure_keeps_existing_failure_contract_and_reason(self):
        exc = app.MissingDatasetsError(['tank/missing', 'tank/also-missing'])
        payload = mqtt.build_payload(self.config, 'create', '0.0.6', exc, 'missing dataset detail', 'run-missing')
        self.assertEqual(payload['status'], 'failure')
        self.assertEqual(payload['exit_code'], 1)
        self.assertFalse(payload['warning'])
        self.assertIn('dataset does not exist', payload['error'])
        self.assertIn('tank/missing', payload['error'])
        self.assertIn('tank/also-missing', payload['error'])
        self.assertIn('missing dataset detail', payload['stderr'])

    def test_capture_is_bounded_and_ignores_separators(self):
        capture = mqtt.ErrorCapture()
        capture.emit(logging.LogRecord('test', logging.ERROR, '', 0, '\n----\n', (), None))
        self.assertEqual(capture.text, '')
        capture.emit(logging.LogRecord('test', logging.ERROR, '', 0, 'x' * 8000, (), None))
        self.assertEqual(len(capture.text), 4096)

    def test_worker_publish_uses_auth_tls_and_no_retain(self):
        publish = Mock()
        paho = types.ModuleType('paho')
        package = types.ModuleType('paho.mqtt')
        package.publish = publish
        config = dict(self.config, username='user', password='secret', tls=True)
        payload = mqtt.build_payload(config, 'create', '0.0.6', None, '', 'run-1')
        context = Mock()
        with patch.dict(sys.modules, {'paho': paho, 'paho.mqtt': package}), \
             patch.object(sys, 'stdin', io.StringIO(json.dumps({'config': config, 'payload': payload}))), \
             patch.object(mqtt.ssl, 'create_default_context', return_value=context):
            mqtt.worker()
        publish.single.assert_called_once()
        kwargs = publish.single.call_args.kwargs
        self.assertFalse(kwargs['retain'])
        self.assertEqual(kwargs['auth'], {'username': 'user', 'password': 'secret'})
        self.assertIs(kwargs['tls'], context)
        self.assertEqual(json.loads(kwargs['payload']), payload)

    def test_publisher_timeout_stdin_and_failure(self):
        with patch.object(mqtt.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            mqtt.publish_report(self.config, {'status': 'success'})
        self.assertEqual(run.call_args.kwargs['timeout'], 15)
        self.assertEqual(json.loads(run.call_args.kwargs['input'])['payload']['status'], 'success')
        self.assertNotIn('broker.example', ' '.join(run.call_args.args[0]))
        with patch.object(mqtt.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'secret')):
            with self.assertRaises(RuntimeError) as exc:
                mqtt.publish_report(self.config, {})
        self.assertNotIn('secret', str(exc.exception))

    def test_disabled_and_dry_run_never_publish(self):
        with patch.object(mqtt, 'publish_report') as publish:
            with mqtt.RunReporter(None, 'create', '0.0.6'):
                pass
            with mqtt.RunReporter(self.config, 'create', '0.0.6', dry_run=True):
                pass
        publish.assert_not_called()

    def test_reporter_publishes_once_and_does_not_mask_failure(self):
        error_logger = logging.Logger('isolated')
        with patch.object(mqtt, 'publish_report') as publish:
            with self.assertRaisesRegex(RuntimeError, 'original failure'):
                with mqtt.RunReporter(self.config, 'delete', '0.0.6') as reporter:
                    reporter.attach(error_logger)
                    error_logger.error('Captured detail')
                    raise RuntimeError('original failure')
        publish.assert_called_once()
        self.assertEqual(publish.call_args.args[1]['status'], 'failure')
        self.assertIn('Captured detail', publish.call_args.args[1]['stderr'])
        self.assertEqual(error_logger.handlers, [])

    def test_publish_errors_preserve_original_outcome(self):
        for failure in [RuntimeError('secret'), subprocess.TimeoutExpired('worker', 15)]:
            with patch.object(mqtt, 'publish_report', side_effect=failure), self.assertLogs('SnapBeforeWatchTower', level='ERROR') as logs:
                with mqtt.RunReporter(self.config, 'create', '0.0.6'):
                    pass
            self.assertNotIn('secret', '\n'.join(logs.output))


if __name__ == '__main__':
    unittest.main()
