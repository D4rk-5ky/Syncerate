# Syncerate 0.4.44 verification

Baseline used for this release: supplied `Syncerate-0.4.43.zip`.

Baseline archive SHA-256:

```text
5b85b205ec2813e18532e942e0f9132b186ffa952f01f682b2c16553092b6ef3
```

## Final `dist/` contract

- `build-pyinstaller.sh` removes previous `.build/` and `dist/` output before a build.
- All generated PyInstaller work/staging material is placed under `.build/pyinstaller-work` and `.build/pyinstaller-dist`.
- PyInstaller never publishes generated build internals directly into final `dist/`.
- The wrapper installs the verified standalone executable as `dist/Syncerate`.
- The wrapper creates `dist/README.md` with the required delivery/build explanation.
- The wrapper counts the top-level `dist/` entries and fails unless there are exactly two: `dist/Syncerate` and `dist/README.md`.
- Any third/unexpected file in final `dist/` is an error.
- The executable must be a regular non-symlink executable; the README must be a regular non-symlink file.
- An exit trap removes `.build/` on success or failure.
- `.gitignore` ignores `.build/` and generated `dist/*` output while explicitly allowing `dist/README.md` to remain trackable.

The packaging regression test exercises the real build wrapper with a fake PyInstaller frontend. It starts with stale content in `dist/`, makes fake PyInstaller emit an unrelated extra staging artifact, and verifies that the final delivery directory contains only:

```text
dist/README.md
dist/Syncerate
```

It also verifies `.build/` is removed.

## Functional checks

- `python3 -m compileall -q Syncerate.py syncerate tests` passed for the release tree.
- `bash -n build-pyinstaller.sh` passed.
- `python3 Syncerate.py --version` reports `Syncerate.py 0.4.44`.
- `python3 Syncerate.py --help` works and continues to document `--conf/-c`, `--dry-run`, and `--version`.
- Configuration/runtime behavior is unchanged by this packaging-only release.
- `config/example-Syncerate.toml` remains the complete categorized example configuration.


## Regression suite

All **134/134** regression tests passed:

- 23 `test_app_and_logging` tests;
- 28 `test_config` tests;
- 8 `test_datasets` tests;
- 20 `test_notifications` tests;
- 4 `test_packaging` tests;
- 48 `test_syncoid_runner` tests;
- 3 `test_system_actions` tests.

The first all-in-one Syncoid run reached the command window while the intentionally slow repeated-progress case was executing after the preceding tests had passed. The uncompleted tail was rerun in smaller bounded groups and all remaining tests passed, covering all 48 Syncoid cases explicitly.

## Documentation/configuration audits

- All 32 fenced TOML examples in `README.md` parse successfully with `tomllib`.
- The loader schema contains 31 supported TOML options and `config/example-Syncerate.toml` contains the same 31 options with no differences.
- AST/code-map audit found 243 production/test class/function definitions and every definition name is represented in `commented_code_map.md`.
- Final checked-in `dist/` entries are exactly `README.md` and `Syncerate`.

## Package comparison and cleanup

Compared with the supplied 0.4.43 baseline:

- baseline regular files: 41;
- 0.4.44 regular files: 42;
- added: `build-pyinstaller.sh` and `dist/README.md`;
- removed: `build_pyinstaller.sh` (renamed to the hyphenated wrapper);
- no application/configuration feature files were removed;
- generated `__pycache__`, `.pyc`, `.pyo`, `.build/`, legacy `build/`, and temporary verification files are excluded before packaging.

`PACKAGE_MANIFEST.json` records SHA-256 hashes and Unix modes against the supplied 0.4.43 archive; its own release hash is intentionally excluded to avoid self-reference.

## Standalone executable limitation

The preserved `dist/Syncerate` executable in the supplied source archive still reports:

```text
Syncerate 0.4.29
```

It is an original project artifact and is **not** a 0.4.44 executable. A truthful new frozen executable could not be produced in this environment because the full PyInstaller build dependencies are unavailable. On a configured build host, install `requirements-build.txt` and run:

```bash
./build-pyinstaller.sh
```

The updated wrapper will recreate `dist/` and leave exactly these two delivery files:

```text
dist/README.md
dist/Syncerate
```

## What was not fully tested

No live ZFS pool, real Syncoid replication, remote SSH host, production MQTT broker/Home Assistant instance, local mail server/delivery path, or real post-success `SystemAction` was exercised for this packaging-only release. Those functional paths remain covered by the existing regression suite.

A real PyInstaller freeze was not performed here. The final-directory publication/cleanup behavior itself is exercised end-to-end with the fake PyInstaller frontend used by `tests/test_packaging.py`.
