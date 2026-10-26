# Syncerate 0.4.54 verification

Date: 2026-10-26. Previous release: `Syncerate-0.4.53.zip`, SHA-256 `2571ca651888e755ab0afea4cc1e7b1b995ca8fb297582a6f6624708c6fbb056`. Original uploaded project: `Syncerate-Syncerate-Next.zip` (0.4.52), SHA-256 `170fc06def2b3eaef3f3329cf9a242022cadd14a8bb2f0007e298ac43744c885`.

## What changed

The live MQTT monitor now detects Paho's CallbackAPIVersion capability. Paho 1.x uses its original client constructor; Paho 2.x explicitly selects callback API VERSION2. The client ID is a keyword in both cases. Connect/disconnect callbacks accept the old/new argument counts using optional trailing parameters. No exception-based fallback hides unrelated constructor failures. Discovery, heartbeat, progress, reconnect and terminal result behavior reuse the same existing monitor implementation.

Every MQTT path was reviewed. Legacy retained success and HA availability, JSON success/failure/dry-run status and failure-wrapper routing already use `publish.multiple()` arguments shared by both library versions. Duplicate rejection uses the shared `publish.single()` helper. Both helpers own their version-appropriate callbacks and were retained. Their actual serialized packets were verified with each installed library.

The source version and build expectations advance by exactly 0.0.1 to 0.4.54. README, full configuration comments, function map and VERSIONING.md describe the current compatibility behavior. The standalone executable was rebuilt with pinned Paho 2.1.0. All 38 config option values, existing flags, both exact disclaimers, replication safety and notification/exit policies are preserved. No original file is removed; one new test module is added.

## Verification results

| Check | Result |
| --- | --- |
| Full suite / actual Paho 1.6.1 | **192/192 passed**, Python 3.12.14; no skipped tests. |
| Full suite / actual Paho 2.0.0 | **192/192 passed**, Python 3.12.14; no skipped tests. |
| Full suite / actual Paho 2.1.0 | **192/192 passed**, Python 3.12.14; no skipped tests. |
| Matrix isolation | Libraries installed in separate workspace locations; their actual imported versions and paths checked. Each run uses one selected Paho installation. |
| New callback regressions | Strict legacy constructor rejects v2-only kwargs; actual 4-argument connect and 3-argument disconnect work. Both old/new refusal and disconnect shapes checked. Unrelated constructor errors are not retried as legacy and stay nonfatal to backup work. |
| All one-shot MQTT paths | Real Paho TCP serialization tested for legacy-only, JSON-only and combined modes, each with real success, failure and dry-run success; topics, payloads, auth fields, QoS and retention checked. Failure wrapper still reports errors when the success switch is false. |
| Live monitor / real packets | 13 retained Discovery definitions, non-retained running/heartbeat/progress, forced socket disconnect and actual reconnect with Discovery refreshed, one optional start event, retained final success result and completed event verified with each installed Paho version. |
| Duplicate rejection / real packets | Real `publish.single()` sends only a non-retained QoS1 duplicate_rejected event; no owner status/last-result publications. |
| Rebuilt executable / real packets | Four complete CLI scenarios pass with bundled Paho 2.1.0: simulated successful replication, dry-run, mismatching-final-pair preflight failure and duplicate-lock rejection. Legacy retained success/availability, JSON, live Discovery/results/events and duplicate routing verified; no retained success signal on dry-run/failure. |
| Existing safety suite | Original 186 regressions remain included: preflight, locks, retry limits, fatal ENOSPC, missing datasets, credentials, progress, notifications, logging and best-effort system actions. |
| Source/binary basic CLI | Both report 0.4.54; help covers every flag; help/version create no runtime files. Required/unknown args and missing config return 2. Config-selected and CLI-forced dry-run avoid prompts/replication/system action; real flock duplicate returns 13; final-pair mismatch returns 1. Simulated two-pair execution reports two completed datasets and 2 MiB. Source CLI also exercised with Python 3.14.4. |
| Compile/build | All 30 Python source/test files plus Syncerate.spec compile; shell syntax passes. Actual one-file Linux x86-64 build with Python 3.12.14, PyInstaller 6.22.2, hooks 2026.7, Pexpect 4.9.0 and Paho 2.1.0. Build's own version/help checks pass. |
| Configuration/docs | All 38 TOML values unchanged; current examples remain complete. Both exact disclaimers preserved. All 345 Python function names represented in the map, with explicit purposes for every new test/fixture function. |
| File preservation | All 51 preceding-release paths and all 51 original uploaded paths preserved; **52 release files**, including tests/test_mqtt_compatibility.py. Complete SHA-256, size and mode accounting for both baselines is in PACKAGE_MANIFEST.json. |
| Clean packaging | dist contains only Syncerate and README.md; .build removed. No bytecode, Python/test/build caches, generated locks, logs, temporary files, dependency installations or scratch scripts enter the zip. |
| Final zip | Exact member set, CRC, every content hash and Unix mode checked against the release tree; source and executable version/help verified again from a fresh extraction. Executables retain 0755; ordinary files use 0644 and directories 0755. Original uploaded DOS entries with unspecified modes are recorded separately and normalized to 0644. |

## Limits and preserved behavior

The MQTT fixture is a small isolated MQTT 3.1.1 loopback packet recorder/acknowledger, not a production broker or a Home Assistant installation. Broker-side ACL rejection, TLS, MQTT v5, real HA entity/UI/automation creation and Pushover delivery were not tested. The change concerns Paho library major versions; it does not add another MQTT wire protocol or transport configuration. Tested library releases are 1.6.1, 2.0.0 and 2.1.0, not every historical 1.x/2.x patch release.

No real ZFS/Syncoid replication, remote SSH/encrypted-key exchange or production mail/system action was performed. Simulated local children test the actual runner without touching datasets. The rebuilt executable bundles Paho 2.1.0; installing another system Paho does not change that embedded dependency. Binary compatibility on other Linux distributions/architectures requires local verification/rebuilding.

Live monitoring remains optional and best-effort, including bounded shutdown. Legacy MQTT errors retain their existing failure policy. Lock ownership/scope, notification switches, QoS/retain, topics, payloads, automatic first-contact host-key acceptance and post-success actions are unchanged. The initial restricted-sandbox packet test could not create sockets; all final matrix/standalone packet checks ran with permitted localhost access and passed.

API review references: [Paho callback migration](https://eclipse.dev/paho/files/paho.mqtt.python/html/migrations.html), [Paho helpers](https://eclipse.dev/paho/files/paho.mqtt.python/html/helpers.html), and [Paho 1.6.1 publisher source](https://github.com/eclipse-paho/paho.mqtt.python/blob/v1.6.1/src/paho/mqtt/publish.py). The separate zip checksum avoids circular archive hashing; the manifest excludes its own current hash.
