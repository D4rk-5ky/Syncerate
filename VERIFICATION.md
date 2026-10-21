# Syncerate 0.4.52 verification

Baseline: the complete supplied `Syncerate-0.4.51.zip`. No original project paths were removed. The existing standalone executable was rebuilt in place from this release's source.

## Checks completed

| Check | Result |
| --- | --- |
| Full regression suite | **186/186 passed** in a single run (176 existing, 10 new transfer-progress tests). |
| Syncoid runner safety tests | **53/53 additionally passed in isolated processes**, including fatal ENOSPC, pipeline cleanup, retry limits, missing datasets, warning classification and credential handling. |
| Progress before EOF | A real Pexpect child is prevented from exiting until a heartbeat publishes its >100% progress. Passed. |
| Supplied example | `(~ 3.3 GB)` + `3,34GiB ... [23,3MiB/s] ... 99%` parses to about 3.3 GiB estimated, 3.34 GiB observed, 23.3 MiB/s, **101.21%**. Comma/period decimals and byte-unit semantics verified. |
| Unknown/reset behavior | Missing/zero estimates, missing rates, unknown counters, CR/LF chunking, final unterminated records, recursive stream changes, new configured pairs and real Broken Pipe retry resets passed. |
| Monitoring isolation | Parser callback exceptions remain nonfatal. Progress refreshes only update the local cache; existing heartbeat/lifecycle publications carry readings. No per-line network traffic. |
| HA Discovery | 13 retained definitions: 12 expiring live sensors (including the four new transfer sensors) and one non-expiring last-result sensor. Existing entity IDs retained; new fields use unknown-safe templates. |
| Python source | All source/test files compile; `--version` reports 0.4.52; `--help` describes all flags and optional transfer monitoring. |
| Source and standalone CLI | Both pass `--help`, `--version`, real CLI dry-run and mismatching-final-dataset preflight (exit 1, no replication). |
| Real Paho network serialization | Both source and rebuilt executable connected to an isolated local MQTT protocol fixture using Paho 2.1.0. Verified 13 Discovery publications, a non-retained heartbeat with 101.21% **while the child is still running**, and a retained success result with final counters. The child exits only after that heartbeat is acknowledged by the test fixture. This is not a production broker/HA test. |
| Standalone build | Built Linux x86-64 one-file `dist/Syncerate` with pinned requirements: PyInstaller 6.22.2, hooks 2026.7, Pexpect 4.9.0, Paho 2.1.0. Embedded version 0.4.52, help and simulated-transfer checks passed. |
| Build wrapper | `bash -n` passed; the build script's own version/help/dist checks passed; `dist/` contains exactly `README.md` and `Syncerate`; `.build/` removed. |
| Configuration | Example parses successfully, and its key set matches all **38** supported options. No new settings/defaults or flags were introduced; comments explain heartbeat progress. |
| Documentation | Current-use README, CLI help, example comments, VERSIONING and function/command map updated. Existing disclaimers preserved. |
| ZIP preservation and integrity | All **50 original file paths** accounted for; **51 release files** including the manifest and one new test file. No removed files. Every archived content hash and Unix mode checked against the manifest; original hashes/modes checked directly against the baseline ZIP. ZIP CRC check passed. |
| Clean package | No Python caches/bytecode, generated locks, build work directories, dependency trees, temporary files or test logs included. |

## Behavior and limits

The four new readings apply to the current **Syncoid send stream**, not the combined remaining size of a recursive pair or whole backup. Syncoid's rounded estimate can be low; progress is deliberately not capped at 100%, and reaching it never declares a backup successful. Multiple streams and retries reset the live measurements. Existing run-wide byte totals still accumulate finished attempts without double-counting output refreshes.

An alive heartbeat can repeat a stale byte/rate observation if transfer output stops. `progress_observed_at` distinguishes a counter observation from a fresh script heartbeat. Missing estimates/counters/rates are unknown; standard output is required (`--quiet` or custom pv options may suppress it). Speed is the last reported rate. Estimates and pv human-readable counters are rounded, so byte amounts and percentages are approximate.

Live ZFS/Syncoid replication, remote SSH, an external production MQTT broker, actual Home Assistant entity creation/UI, production mail and Pushover delivery were **not tested**. Simulated children and fake/local protocol transports were used. The rebuilt executable is Linux x86-64 and was exercised in this environment; compatibility with other distributions/architectures requires local verification or rebuilding. The existing per-TOML lock scope and cross-host/shared-filesystem limitations are unchanged.
