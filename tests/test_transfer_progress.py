"""Verify live progress is observational and available before child EOF."""
import json
from pathlib import Path
import shlex
import tempfile
import threading
import unittest
from unittest import mock

from syncerate.live_status import LiveBackupMonitor, discovery_messages
from syncerate.models import DatasetPair, ReplicationSummary
from syncerate.syncoid_runner import TransferByteCounter, run_replications
from tests.helpers import make_config, make_logger, no_logging_context, write_executable
from tests.test_live_status import FakeClient


class TransferProgressTests(unittest.TestCase):
    def test_user_output_chunked_with_comma_decimal_and_over_estimate(self):
        snapshots = []
        counter = TransferByteCounter(progress_callback=snapshots.append)
        output = ('INFO: Sending incremental remote:pool/Joplin@old ... new to backup/Joplin (~ 3.3 GB):\r\n'
                  'mbuffer: warning: HOME environment variable not set - unable to find defaults file\r\n'
                  '3,34GiB 0:02:26 [23,3MiB/s] [===============================> ]  99%\r')
        for char in output:
            counter.write(char)
            counter.flush()  # A Pexpect read boundary is not a physical line boundary.
        result = snapshots[-1]
        self.assertEqual(result['current_dataset_estimated_bytes'], round(3.3 * 1024**3))
        self.assertEqual(result['current_dataset_transferred_bytes'], round(3.34 * 1024**3))
        self.assertEqual(result['current_dataset_bytes_per_second'], round(23.3 * 1024**2))
        self.assertEqual(result['current_dataset_progress_percent'], 101.21)
        self.assertIn('backup/Joplin', result['current_transfer'])
        self.assertEqual(counter.finish(), (round(3.34 * 1024**3), True))

    def test_estimate_units_follow_syncoid_binary_scaling(self):
        for unit, scale in [('B', 1), ('KB', 1024), ('MB', 1024**2), ('GB', 1024**3),
                            ('TB', 1024**4), ('GiB', 1024**3)]:
            with self.subTest(unit=unit):
                snapshots = []
                counter = TransferByteCounter(progress_callback=snapshots.append)
                counter.feed(f'INFO: Sending full pool/a@s (~ 1,5 {unit}):\n')
                self.assertEqual(snapshots[-1]['current_dataset_estimated_bytes'], round(1.5 * scale))
                self.assertIsNone(snapshots[-1]['current_dataset_transferred_bytes'])

    def test_missing_or_zero_estimate_and_missing_rate_stay_unknown(self):
        for heading in ['INFO: Resuming interrupted zfs send/receive from pool/a to backup/a',
                        'INFO: Sending full pool/a@s (~ 0 KB):']:
            with self.subTest(heading=heading):
                snapshots = []
                counter = TransferByteCounter(progress_callback=snapshots.append)
                counter.feed(heading + '\n1MB 0:00:01 [ --- B/s] [=> ]\r')
                result = snapshots[-1]
                self.assertEqual(result['current_dataset_transferred_bytes'], 1_000_000)
                self.assertIsNone(result['current_dataset_progress_percent'])
                self.assertIsNone(result['current_dataset_bytes_per_second'])
        counter = TransferByteCounter(progress_callback=snapshots.append)
        counter.feed('1MiB 0:00:01 [1MiB/s]\r')
        self.assertIsNone(snapshots[-1]['current_dataset_estimated_bytes'])

    def test_new_recursive_stream_resets_values_and_sums_each_counter_once(self):
        snapshots = []
        counter = TransferByteCounter(progress_callback=snapshots.append)
        counter.feed('INFO: Sending oldest full snapshot pool/a@s (~ 1 MB) to new target filesystem:\n'
                     '512KiB 0:00:01 [512KiB/s]\r1MiB 0:00:02 [512KiB/s]\r'
                     '1MiB 0:00:02 [512KiB/s]\r'
                     'INFO: Sending incremental pool/a/child@old ... new to backup/a/child:\n')
        for key in ['estimated_bytes', 'transferred_bytes', 'bytes_per_second']:
            self.assertIsNone(snapshots[-1]['current_dataset_' + key])
        self.assertIn('/child', snapshots[-1]['current_transfer'])
        counter.feed('2MiB 0:00:02 [1MiB/s]')  # EOF without final CR/LF.
        self.assertEqual(counter.finish(), (3 * 1024**2, True))
        self.assertEqual(snapshots[-1]['current_dataset_transferred_bytes'], 2 * 1024**2)

    def test_warning_or_debug_heading_does_not_reset_real_stream(self):
        snapshots = []
        counter = TransferByteCounter(progress_callback=snapshots.append)
        counter.feed('INFO: Sending incremental pool/a@s ... s2 (~ 2 MB):\n'
                     '1MiB 0:00:01 [1MiB/s]\r'
                     'WARNING: Sending full explanatory text (~ 999 GB)\n'
                     'DEBUG: Sending full explanatory text (~ 999 GB)\n')
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(counter.finish(), (1024**2, True))

    def test_instrumentation_exception_cannot_break_transfer_accounting(self):
        callback = mock.Mock(side_effect=RuntimeError('monitor unavailable'))
        counter = TransferByteCounter(progress_callback=callback)
        with self.assertLogs('syncerate.syncoid_runner', level='WARNING'):
            counter.feed('INFO: Sending full pool/a@s (~ 1 MB):\n1MiB 0:00:01 [1MiB/s]\r')
        self.assertEqual(counter.finish(), (1024**2, True))
        callback.assert_called_once()

    def test_progress_is_cached_until_heartbeat_and_reset_for_next_pair(self):
        monitor = LiveBackupMonitor(make_config(), make_logger('progress-cache'))
        client = FakeClient(); monitor._client = client; monitor._connected.set()
        summary = ReplicationSummary(total_datasets=2)
        monitor.progress('started', DatasetPair('pool/a', 'backup/a', ()), summary)
        counter = TransferByteCounter(progress_callback=monitor.transfer_progress)
        count = len(client.messages)
        counter.feed('INFO: Sending full pool/a@s (~ 1 MB):\n2MiB 0:00:02 [1MiB/s]\r')
        self.assertEqual(len(client.messages), count)
        payload = json.loads(monitor._payload())
        self.assertEqual(payload['current_dataset_progress_percent'], 200)
        self.assertIsNotNone(payload['progress_observed_at'])
        monitor.finish('failed', 12, error='out of space')
        final = [p for t, p, _, _ in client.messages if t == monitor.last_result_topic][-1]
        self.assertEqual(final['current_dataset_progress_percent'], 200)
        self.assertEqual(final['status'], 'failed')
        monitor.stop()
        monitor = LiveBackupMonitor(make_config(), make_logger('next-pair'))
        monitor.transfer_progress(payload)
        monitor.progress('started', DatasetPair('pool/b', 'backup/b', ()), summary)
        next_payload = json.loads(monitor._payload())
        for key in ['current_dataset_progress_percent', 'current_dataset_estimated_bytes', 'progress_observed_at']:
            self.assertIsNone(next_payload[key])

    def test_discovery_uses_existing_status_topic_and_unknown_safe_templates(self):
        monitor = LiveBackupMonitor(make_config(), make_logger('discovery-progress'))
        sensors = [json.loads(m['payload']) for m in discovery_messages(monitor)]
        new = [s for s in sensors if s['unique_id'].split(monitor.backup_id + '_')[1].startswith('current_dataset_')]
        self.assertEqual(len(new), 4)
        self.assertEqual({s['unit_of_measurement'] for s in new}, {'B', '%', 'B/s'})
        self.assertTrue(all(s['state_topic'] == monitor.status_topic for s in new))
        self.assertTrue(all(s['expire_after'] == 180 for s in new))
        self.assertTrue(all('float(0)' not in s['value_template'] for s in new))
        self.assertIn('current_transfer', next(s for s in new if s['unit_of_measurement'] == '%')['json_attributes_template'])

    def test_real_child_requires_heartbeat_ack_before_it_can_finish(self):
        with tempfile.TemporaryDirectory() as td:
            ack = Path(td) / 'heartbeat-ack'
            script = write_executable(Path(td) / 'fake_syncoid.py',
                'import pathlib, sys, time\n'
                "print('INFO: Sending incremental pool/a@s ... new to backup/a (~ 3.3 GB):', flush=True)\n"
                "sys.stdout.write('3,34GiB 0:02:26 [23,3MiB/s] [======>] 99%' + chr(13)); sys.stdout.flush()\n"
                f'ack = pathlib.Path({str(ack)!r})\n'
                'deadline = time.monotonic() + 3\n'
                'while not ack.exists() and time.monotonic() < deadline: time.sleep(0.01)\n'
                'sys.exit(0 if ack.exists() else 9)\n')
            cfg = make_config(syncoid_command=f'{shlex.quote(script)} SourceDataSet DestDataSet', live_heartbeat_seconds=0.03)
            monitor = LiveBackupMonitor(cfg, make_logger('real-progress'))
            class AckClient(FakeClient):
                def publish(self, topic, payload, qos=0, retain=False):
                    value = json.loads(payload)
                    if topic == monitor.status_topic and (value.get('current_dataset_progress_percent') or 0) > 100:
                        ack.touch()
                    return super().publish(topic, payload, qos, retain)
            client = AckClient(); monitor._client = client; monitor._connected.set()
            heartbeat = threading.Thread(target=monitor._heartbeat, daemon=True); heartbeat.start()
            try:
                result = run_replications(cfg, no_logging_context(), [DatasetPair('pool/a', 'backup/a', ())],
                    None, make_logger('real-runner'), progress_callback=monitor.progress,
                    transfer_callback=monitor.transfer_progress)
                self.assertTrue(ack.exists())
                self.assertEqual(result.completed_datasets, 1)
                self.assertEqual(result.transferred_bytes, round(3.34 * 1024**3))
                live = [p for t, p, _, r in client.messages if t == monitor.status_topic
                        and p['completed_datasets'] == 0 and p.get('current_dataset_progress_percent')]
                self.assertTrue(live)
                self.assertFalse(any(r for t, p, _, r in client.messages if t == monitor.status_topic))
            finally:
                monitor._stop_signal.set(); heartbeat.join(timeout=1); monitor.stop()

    def test_retry_starts_with_unknown_measurements_instead_of_old_estimate(self):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / 'attempted'
            script = write_executable(Path(td) / 'retry.py',
                'from pathlib import Path\n'
                f'marker = Path({str(marker)!r})\n'
                'if not marker.exists():\n'
                '    marker.touch()\n'
                "    print('INFO: Sending full pool/a@s (~ 1 MB):', flush=True)\n"
                "    print('1MiB 0:00:01 [1MiB/s]', flush=True)\n"
                "    print('broken pipe', flush=True)\n"
                'else:\n'
                "    print('INFO: Resuming interrupted zfs send/receive from pool/a to backup/a', flush=True)\n"
                "    print('2MiB 0:00:02 [1MiB/s]', flush=True)\n")
            cfg = make_config(syncoid_command=f'{shlex.quote(script)} SourceDataSet DestDataSet',
                              retry_broken_pipe=True, broken_pipe_retry_count=1,
                              broken_pipe_retry_wait_seconds=0)
            snapshots = []
            result = run_replications(cfg, no_logging_context(), [DatasetPair('pool/a', 'backup/a', ())],
                                      None, make_logger('retry-live'), transfer_callback=snapshots.append)
            self.assertEqual(result.completed_datasets, 1)
            self.assertEqual(result.transferred_bytes, 3 * 1024**2)
            resets = [x for x in snapshots if not x['current_transfer']]
            self.assertEqual(len(resets), 2)
            self.assertTrue(all(x['current_dataset_transferred_bytes'] is None for x in resets))
            self.assertEqual(snapshots[-1]['current_dataset_transferred_bytes'], 2 * 1024**2)
            self.assertIsNone(snapshots[-1]['current_dataset_estimated_bytes'])
            self.assertIsNone(snapshots[-1]['current_dataset_progress_percent'])


if __name__ == '__main__':
    unittest.main()
