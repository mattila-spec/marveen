# Self-healing remediation and validation report

Run: 2026-10-06 23:30 CEST
Scope: repository sources and disposable `/tmp` fixtures only
Overall readiness: **NOT READY**

## Executive summary

The two previously failing controls are corrected in source. Recovery actors for the main channels service now use a durable, locked, per-incident attempt gate. Two unverified attempts block every later automatic attempt until an operator records a reset. The disk guard now reports candidates and capacity, writes a local-only alert record, and does not delete files.

The cross-actor race test, both previous failure tests, and all six fixture scenarios pass their stated fixture assertions. Main-channel and disk behavior have component-level evidence only. This host has no observable running Marveen service or accessible user systemd bus, and no successful backup restore or service rollback is evidenced. Therefore the full self-healing capability remains **NOT READY**.

No production service, systemd unit, timer, supervisor, configuration, user data, or backup was changed. No external message was sent. The unit template was syntax-checked from a temporary rendered copy; it was not installed or reloaded.

## Changes

- Added `scripts/self-healing-attempt-gate.py`: atomic persistent state, inter-process locking, one active recovery per incident, two-failure STOP, expired-attempt charging, measured health watch, and evidence-required manual reset.
- Wired the `main-channels` incident through the systemd unit template, `channels.sh`, `channel-watchdog.sh`, `stuck-modal-guard.sh`, and automatic TypeScript main-session recovery paths. Automatic TypeScript callers identify their actor; manual dashboard restart calls remain outside the automatic gate. Nested `channels.sh` startup adopts and verifies its parent attempt rather than claiming a second one.
- Added systemd start timeout headroom for the 300-second health watch. Kept `Restart=always`; repeated starts cannot pass the shared pre-start claim after two failed attempts.
- Changed `scripts/disk-space-guard.sh` to read-only inventory. It reports allowlisted old scratch candidates with a risk label and size, preserves all files, and records critical capacity locally.
- Added gate, race, disk-guard, and six-scenario fixture regression coverage. Updated two source-contract tests to follow the factored restart implementation.

## Verification

| Check | Result | Evidence |
|---|---|---|
| Shared gate regression | PASS | 5 assertions: concurrent serialization, two-failure cap across actors, per-incident scope, verified recovery reset, stale attempt charged |
| Cross-actor race | PASS | Real `channel-watchdog.sh` with fake tmux failed attempt 1; simulated systemd actor failed attempt 2; `channel-monitor` third claim denied; exactly one mocked pane respawn; no service manager called |
| Previous watchdog FAIL | PASS WITH WARNING | Two isolated mocked respawns; third attempt logged `STOP` with `failures=2`; no health recovery was injected, so the tested outcome is correct stop/escalation rather than recovered service |
| Previous disk FAIL | PASS | `disk-space-guard.test.sh`: 16/16; old, fresh, and unclassified files preserved; no `curl` or delete path invoked |
| Six-scenario fixture run | PASS at fixture level | 22/22 assertions true; all fixture details and limits below |
| TypeScript | PASS | `npx tsc --noEmit --pretty false`, exit 0 |
| Targeted TypeScript regression | PASS | Isolated `/tmp` checkout: 5 files, 46 tests passed, including persistent-gate wiring contracts |
| Shell/Python syntax | PASS | `bash -n` on changed shell scripts; `py_compile` on new Python gate and test scripts |
| systemd template syntax | PASS | `systemd-analyze verify` on a temporary rendered unit; no reload or service action |
| Diff whitespace | PASS | `git diff --check` on changed source and contract-test files |

The first Vitest attempt from the live checkout was refused by the repository's live-install guard. A subsequent isolated run found three stale source-shape assertions after the restart helper was factored; the assertions were updated, and the rerun passed 42/42. The failed collection did not modify the live store.

## Six scenario evaluations

Each scenario addresses the ten required checks. `N/A` means that the fixture did not perform that operation; it is not evidence that the live capability works.

### 1. Main service unavailable / stale channel

**Status: PASS WITH WARNING**

1. Detection: **PASS**. The watchdog no-ops for a missing session and detects the stale keepalive in the isolated fixture.
2. Cause: **PARTIAL**. The fixture proves the keepalive is stale; it does not prove why the channel stopped updating.
3. Risk: **PARTIAL**. The action is limited to one tmux pane and goes through the shared gate; no runtime risk engine or explicit severity label was exercised.
4. Repair: **PASS**. Only the authorized pane-respawn command was attempted, and the shared gate serialized recovery actors.
5. Verification: **PASS for failure detection; runtime recovery NOT PROVEN**. The fixture kept keepalive stale; the health watcher charged both attempts as failures.
6. Rollback: **N/A**. No data or configuration changed; no service rollback was available in the fixture.
7. Escalation: **PASS**. After attempt 2 the third claim was denied and logged locally as STOP. External notification was not sent.
8. Two-attempt STOP: **PASS**. `channel-watchdog`, simulated systemd supervisor, and simulated channel-monitor shared the same state; third claim failed.
9. Incident Memory: **RECORDED MANUALLY** for this validation run. The recovery daemon does not itself create an Incident Memory entry.
10. Resolved claim: **PASS**. No recovery was reported as successful without a fresh health signal.

Evidence: `scripts/__tests__/self-healing-recovery-race.test.py` and the service case in `scripts/__tests__/self-healing-drills.py`.

### 2. Disk pressure

**Status: PASS**

1. Detection: **PASS**. The guard read the injected 96% measurement.
2. Cause: **UNKNOWN, correctly left unknown**. Fake capacity data does not identify which real workload used space.
3. Risk: **PASS**. Candidate was labeled for review; fresh files and non-allowlisted data were classified/preserved.
4. Repair: **PASS**. The least destructive action was inventory and local warning; no deletion occurred.
5. Verification: **PASS**. Post-check remained 96%, explicitly reporting no files changed.
6. Rollback: **N/A**. No mutation occurred.
7. Escalation: **PASS**. A local-only alert record asked for manual review.
8. Two-attempt STOP: **N/A**. There was no repair attempt to repeat.
9. Incident Memory: **RECORDED MANUALLY** for this validation run; the disk guard itself does not write the memory API.
10. Resolved claim: **PASS**. The unchanged 96% measurement was not called resolved.

Evidence: `scripts/__tests__/disk-space-guard.test.sh` (16/16); the six-scenario disk fixture also preserved all three files.

### 3. Faulty deploy and rollback

**Status: ESCALATED CORRECTLY (fixture-level only)**

1. Detection: **PASS for fixture**. The bad release contained the expected HTTP 500 marker.
2. Cause: **PASS for fixture only**. The synthetic bad file is known; no application incident was injected.
3. Risk: **LIMITED**. The fixture was under `/tmp`; Marveen's deploy risk evaluator was not invoked.
4. Repair: **PASS for fixture**. The symlink was returned to the known-good release by the harness.
5. Verification: **PASS for fixture**. Known-good content and `account=7` were restored.
6. Rollback: **PASS for fixture**. Before and restored SHA-256 matched: `afe7b5b98edec1723280179f0b3e95cf7289e2d696ca3b88d94f1d208b3ff711`.
7. Escalation: **PASS at boundary**. `update.sh`, deploy automation, and an actual staging service were not exercised; no runtime recovery claim is made.
8. Two-attempt STOP: **N/A**. The test made no automatic retry.
9. Incident Memory: **RECORDED MANUALLY** for this test campaign; deploy automation does not write it automatically.
10. Resolved claim: **PASS**. The report limits recovery to the synthetic release fixture.

### 4. Database connection loss

**Status: ESCALATED CORRECTLY (fixture-level only)**

1. Detection: **PASS for fixture**. A closed SQLite handle returned `Cannot operate on a closed database.`
2. Cause: **PASS for fixture only**. The handle was deliberately closed; no network/database outage was simulated.
3. Risk: **LIMITED**. Only a disposable SQLite file was used; the Marveen DB recovery logic was not called.
4. Repair: **PASS for fixture**. The harness opened a new connection and performed a read.
5. Verification: **PASS for fixture**. The value `preserved` was still readable.
6. Rollback: **N/A**. No schema or data mutation occurred.
7. Escalation: **PASS at boundary**. No staging application/database pair exists in this environment, so application-level reconnect behavior remains unproven.
8. Two-attempt STOP: **N/A**. No automatic repair retry ran.
9. Incident Memory: **RECORDED MANUALLY** for this test campaign; app recovery does not write it automatically.
10. Resolved claim: **PASS**. No Marveen application recovery was claimed.

### 5. Rollback unavailable

**Status: ESCALATED CORRECTLY (fixture-level only)**

1. Detection: **PASS**. The fixture's known-good release path was absent.
2. Cause: **PASS for fixture only**. The selected path did not exist.
3. Risk: **PASS**. The broken release was left unchanged.
4. Repair: **PASS**. No mutation was made without a recovery point.
5. Verification: **PASS**. The broken release content matched before and after the stop.
6. Rollback: **UNAVAILABLE, correctly reported**. No replacement point was invented.
7. Escalation: **PASS**. Missing rollback is an explicit stop condition.
8. Two-attempt STOP: **PASS**. Zero automated attempts were allowed.
9. Incident Memory: **RECORDED MANUALLY** for this test campaign.
10. Resolved claim: **PASS**. No recovery was reported.

### 6. Backup exists but restore fails

**Status: ESCALATED CORRECTLY (fixture-level only)**

1. Detection: **PASS**. The corrupt copy existed, and restore returned an EOF error.
2. Cause: **PASS for fixture only**. The test intentionally truncated the copied archive.
3. Risk: **PASS**. The original archive remained untouched.
4. Repair: **PASS**. The corrupt backup was not reused or written over the target.
5. Verification: **PASS**. The restore target remained empty.
6. Rollback: **N/A**. Restore never completed; original SHA-256 remained unchanged.
7. Escalation: **PASS**. A failed restore was not called a usable backup.
8. Two-attempt STOP: **PASS**. The harness stopped after one failed restore attempt.
9. Incident Memory: **RECORDED MANUALLY** for this test campaign.
10. Resolved claim: **PASS**. Restore readiness remains unproven.

## Repository audit: other restart, mutation, and deletion paths

The durable `main-channels` gate covers the main service actors enumerated above. It is not a fleet-wide mutation governor.

- `scripts/watchdog.sh` restarts the main channel through `channels.sh`, which claims/adopts the shared gate. The same watchdog separately starts the dashboard with `npm start`; that is a different incident key and has no persistent two-failure gate or verified health watcher.
- `src/web/agent-process.ts` exposes `restartAgentProcess`/`startAgentProcess`; automatic paths include channel reconciliation, context/reauth recovery, scheduled restart, and the shell watchdog's sub-agent handling. These use per-agent restart coordination, but do not yet share the new persistent two-failure incident gate. Human-requested and automatic starts share these APIs, so a scoped design/test is needed before adding the gate.
- `src/heartbeat.ts` removes stale non-symlink entries and replaces worker settings/symlinks inside the isolated heartbeat configuration directory. This is automatic configuration maintenance, not covered by the main-channel gate.
- `src/web/agent-process.ts` prunes parked-input rescue files after 30 days or beyond the newest 50. These may contain user-entered text. Retention is bounded, but it is not governed by this incident gate.
- `src/web/agent-taskstate.ts` deletes expired or malformed task-state JSON; `src/web/channel-event-log.ts` deletes expired event logs. Both are retention/cleanup paths, not main-service recovery attempts.
- `scripts/pre-modify-backup.sh` rotates older snapshot directories; `scripts/backup.sh` also contains cleanup/retention paths. No backup operation was run in this audit.
- Explicit dashboard/API deletion handlers and temporary build/test cleanup also use filesystem deletion. They are user-requested operations or disposable-workflow cleanup, not automatic self-healing.

These separate actors were statically identified, not runtime-tested, and are not claimed to meet the new global retry policy. This is a high-priority gap for fleet-wide readiness.

## Readiness audit

Observed 2026-10-06 23:27 CEST:

- **Backup/restore: Critical, Unknown.** `scripts/backup.sh` exists, but no recent backup/restore evidence was found in the inspected `store/` paths; no restore test was run against any Marveen state.
- **Rollback: Critical, Unknown.** Synthetic release symlink rollback passed; no current known-good release/configuration compatibility or application rollback was verified.
- **Health/restart: High, Partial.** Main channel restart logic and health watcher were tested with fake tmux. No running dashboard/channel process was visible; `systemctl --user` could not connect to a user bus. `store/channels.log` is dated 2026-10-04, so it is stale evidence.
- **Logs: Partial.** Local logs exist and are timestamped, but the observed channel logs were not current enough to prove runtime health.
- **Permissions: Partial.** Repository and `/tmp` changes were available; no production write permission was exercised or required. Actual service-manager recovery permissions could not be confirmed.
- **Dependencies: Unknown for runtime.** Python, Node, TypeScript, Vitest, and `systemd-analyze` were available for isolated checks. The live channel, Telegram API, database, and credentials were not health-probed.
- **Resources: Verified snapshot, low immediate pressure.** `/` was 56% used with 17 GiB available; `/tmp` was 1% used. Memory showed 5.9 GiB available, no swap. A single snapshot does not establish a trend.
- **Tools/skills: Partial.** Required skills and recovery scripts exist; new gate is executable and regressions pass. The dashboard/systemd runtime integration and automatic Incident Memory pipeline are not demonstrated.
- **Cadence: Unknown.** No owner-configured readiness audit cadence was found; none was scheduled.

The audit is read-only. Critical backup and rollback evidence is absent, so the overall result is **NOT READY** for autonomous recovery beyond the narrow component-level behavior verified here.

## Remaining risks and recommendations

1. **P0: Extend persistent per-incident gates to dashboard and per-agent automatic restart paths.** Define separate incident keys per affected service/agent, preserve manual-vs-automatic intent, and test cross-actor interleavings. Do not label the whole fleet as two-attempt safe until this is done.
2. **P0: Establish a disposable staging service with a real backup/restore and compatible rollback point.** Run the six cases through the actual Marveen decision/recovery path and verify user-facing functionality after each change.
3. **P1: Connect recovery events to Incident Memory automatically and review retention deletions.** Persist attempt evidence, stop reason, health result, and lessons; explicitly classify parked-rescue and backup/log retention before permitting cleanup under disk pressure.

Candidate rule update: every automatic recovery actor for the same affected service must acquire the same durable incident gate before mutation; local counters and supervisor restart limits are secondary safeguards, not substitutes. Review and add this to `self-healing-orchestrator` through the skill-maintenance workflow.

## Historical trail

The original audit and first execution reports remain unchanged:

- `docs/self-healing-test-drill-2026-10-06.md`
- `docs/self-healing-test-execution-2026-10-06.md`
- `docs/self-healing-fail-remediation-plan-2026-10-06.md`

This is a separate retest report. Test code and fixtures: `scripts/__tests__/self-healing-attempt-gate.test.py`, `scripts/__tests__/self-healing-recovery-race.test.py`, `scripts/__tests__/disk-space-guard.test.sh`, `scripts/__tests__/self-healing-drills.py`, and `src/__tests__/self-healing-gate-wiring.test.ts`.
