# Syncerate 0.4.30 verification

## Change and operation

The supplied log reports `cannot receive incremental stream: out of space`. The original monitor used an unlimited Pexpect wait without matching this diagnostic, so a stalled Syncoid pipeline never reached the existing error handler.

The source release recognizes explicit space/quota diagnostics, stops the owned local process group, logs the failure, attempts enabled error notifications, skips later datasets/system actions, and returns **12**. Storage errors never become Broken Pipe warning-success. Existing intended snapshot-recovery exceptions remain supported; generic warning precedence was corrected to preserve those exceptions.

Error MQTT requires `MQTT_JSON_Status = Yes` and a dedicated `mqtt_json_topic`. `Use_MQTT` remains success-only. Email uses the configured `Mail` recipient. Each mail attempt/MQTT batch defaults to a 30-second deadline via optional positive-integer `NotificationTimeoutSeconds`; cleanup can add a few seconds. Existing configurations work without adding this option.

## Checks completed

- 86 regression tests passed: the existing 70 tests plus 16 new storage-failure/notification cases. Real temporary PTY child processes exercise stuck receives, split messages, absent final newline, quota variants, storage-failure precedence, and a stubborn pipeline helper after its leader exits.
- Failure-path integration verifies exit 12, error details in email with logs enabled/disabled, non-retained JSON failure, no next dataset, and no success-only system action.
- The real source CLI and spawned notification workers delivered a failure packet to a local MQTT broker stub and invoked a fake local mail command with the correct recipient/body. No production notifications were sent.
- Timeout tests cover a sleeping fake mail process and a local TCP listener that never answers MQTT CONNECT. Secondary MQTT failure preserves the original storage error and leaves the mail path available.
- Compiled all 23 Python files without generating distributable bytecode. Bash syntax check passed for the build wrapper.
- CLI checks passed: `--version` reports 0.4.30, `--help` exits 0, missing/unknown arguments exit 2, and a missing config exits 2.
- Importing the compatibility entry point is silent and does not start application work.
- All 27 available configuration options appear in the complete example and README. Every Python class/function name appears in the commented code map; the map explains the runtime functions, subprocess commands, and new test cases.
- All original Python function/class names remain present. Previous VERSIONING entries remain unchanged.
- The final package preserves all 40 original regular-file paths: 26 unchanged and 14 updated. Five new files bring the package to 45 files. No original file was removed.
- Zip CRC, per-file SHA-256, permissions, manifest comparison, and absence of bytecode/build/cache/temporary entries are checked during packaging. `PACKAGE_MANIFEST.json` contains the original and release inventories and changed/added classifications; it excludes its own hash to avoid recursion.

## Environment and limits

Tests ran on macOS using Python 3.9, Pexpect 4.9.0, and Paho MQTT 2.1.0. Python dependencies were installed only in an isolated workspace test environment and are not bundled in the source archive.

Live Linux ZFS pool exhaustion, quotas, remote SSH/Syncoid, real SMTP/local mail delivery, production MQTT/Home Assistant, and Linux PyInstaller builds could not be tested here. Some macOS sandbox cleanup attempts logged permission errors when signalling already-terminated notification groups; the timeout tests still completed and the separate stubborn-helper heartbeat test verified termination. Linux process behavior needs a test on your host.

This is explicit diagnostic detection, not a general silent-hang watchdog. Local process-group cleanup does not guarantee termination of detached groups, remote processes, or uninterruptible kernel I/O. Syncerate performs no new snapshot deletion, rollback, or forced receive-abort operation.

## Run the fixed version

Use the source entry point from the extracted project:

```bash
python3 Syncerate.py --version
python3 Syncerate.py --conf /path/to/Syncerate.cfg
```

Keep the adjacent `syncerate/` package with `Syncerate.py`; copying only the entry point is insufficient. The README documents dependencies and rebuilding.

**The supplied `dist/Syncerate` Linux x86-64 executable is preserved unchanged and does not contain the fix.** It must be rebuilt on a compatible Linux host to run this release as a standalone binary. Do not use that preserved binary to test the fix.

Original binary SHA-256: `03fb943defa8b5b3be04663f8131704be807f523bf4d197f85e07be2c3f934bb`.
