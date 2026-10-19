# Syncerate 0.4.50 verification

## Baseline and scope

Baseline: the previously delivered `Syncerate-0.4.49.zip` containing **45 regular files**. This release strengthens preflight dataset-name validation and the way an invalid list is reported over mail, MQTT, terminal and logs. No old files have been removed. The new file is `tests/test_dataset_validation_reporting.py`. Original-file and release SHA-256 hashes, file modes, and changes are recorded in `PACKAGE_MANIFEST.json`, excluding the self-referential manifest final hash.

## Checks completed

- **163 tests passed total**: all **110 non-Syncoid-runner tests** completed successfully in one unittest run; all **53 Syncoid-runner tests** passed in separate subprocesses, as recorded in the isolated-runner report. The monolithic full-suite attempt **stalled in Pexpect** and was interrupted, not claimed as an uninterrupted pass. The independent runs cover every test.
- New regression tests confirm detection of incorrect **final list entries**, mixed matching/mismatching pairs, unequal-length surplus entries, trailing slashes, proper exclusion of per-destination command arguments, and a mismatch with `--dry-run`. The app reports exit **1** before credential resolution, Syncoid, `SystemAction` or other transfer work.
- End-to-end tests (with fake configured mail and MQTT) verify non-retained failure JSON on the dedicated or legacy error topic, structured complete `mismatching_datasets` and `matching_datasets` lists, added mismatch entries in `failed_datasets`, and all pairs in mail with mismatches at its **top**. With file logging enabled, `.log` and `.err` are attached and contain the same validation report; with logging disabled the complete report is still in the email. The terminal ends in the complete audit, after notification log messages.
- A separate **real source CLI subprocess** check with actual TOML and dataset files confirmed a final-item mismatch returns `1`, never starts the fake Syncoid child, and ends terminal output with the complete mismatch/match summary.
- `python3 -B Syncerate.py --version` printed `Syncerate.py 0.4.50`; `--help` explained the validation and flags. All application and test `.py` files passed syntax compilation without writing bytecode, and `bash -n build-pyinstaller.sh` passed. The build wrapper smoke check with simulated PyInstaller passed among the non-runner tests.
- The TOML loader's **31 supported options** are still covered by the complete example; no new settings or default changes. `README.md` retains both liability disclaimers, documents **current behavior only**, and describes failure email/MQTT/terminal reporting. `VERSIONING.md` and `commented_code_map.md` were updated.
- The final ZIP was compared against **all 45 original files** including their SHA-256 hashes and Unix modes, and tested for ZIP integrity, accidental temporary/cache files, and correctness of the included final release manifest.

## Limitations

- Live ZFS replication, real datasets running out of space, production SSH, actual mail command delivery, and actual MQTT broker delivery were **not** tested. Notification routing is verified with mocks and local CLI execution.
- Backup locking remains per canonical TOML path rather than across TOML files with overlapping ZFS destinations, or across hosts unless POSIX shared filesystem locking works. Do not remove `.toml.lock` while a backup may be running.
- The preserved `dist/Syncerate` executable is **still version 0.4.29**, inherited from earlier supplied archives. It **does not include any 0.4.50 dataset-reporting change** or subsequent fixes since 0.4.29. Build dependencies were not installed here and no new standalone executable was built. Run the **0.4.50 Python source** or install the build dependencies and execute `./build-pyinstaller.sh` on a compatible Linux machine.
