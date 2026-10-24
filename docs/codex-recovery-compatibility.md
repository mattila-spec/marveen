# Codex recovery compatibility

The owner's approved operating rules remain in AGENTS.md without text changes.
This follow-up preserves the installed main-channel incident budget on the
Codex-capable release candidate. It does not switch the main backend to Claude.

Dashboard Codex workers receive the trusted project rule root separately from
their working directory. Heartbeat and digest sandboxes retain their isolated
cwd while loading the canonical project source; a missing project source fails
closed even if the sandbox contains its own instruction file. Direct worker CLI
calls still use their provided cwd when no explicit project source is supplied.

## Recovery ownership

The Python gate serializes claims across processes using one `main-channels`
incident and an atomic, private state file. Two failed attempts stop further
automatic recovery. Verified stable session health resets that incident; a
manual restart does not silently reset its counters. Invalid persisted state
fails closed. Health checks use an exact tmux session target and a fresh
keepalive newer than the current attempt for Claude. Codex instead requires
a status snapshot from the current launch, a live PID and its responding local
Unix socket; idle status does not need periodic rewrites.

Dashboard automatic hard restarts, scheduled fresh starts, resume/fresh recovery,
MCP reconnect, inbound recovery, context/usage fallback and reauthentication
share that budget. Existing scheduling holds, grace windows, supervisor
deduplication, fleet-freeze controls and exact tmux targets remain in place.
A missing Codex pane delegates to the normal channel launcher with inherited
ownership; it cannot accidentally claim the same incident twice.

The shell launchers and generic channel watchdog use the same gate. A direct
Codex preflight checks canonical rules before authentication and before replacing
the existing pane. The Codex watchdog can work without a Claude executable.
The Claude modal guard skips Codex hosts: Escape and /mcp are TUI actions, not
Codex RPC control messages. Its existing Claude recovery path remains budgeted.
The systemd template owns its pre-start claim and post-start verifier; inherited
claim IDs and supervisor ownership are checked before child startup.

## Installed disk-guard policy

Preserve the installed read-only disk guard as a separate compatibility change.
It inventories old scratch candidates and records a local alert, but never
deletes candidates or sends an external notification. Upstream automatic cleanup
and external notification must not be reintroduced by this release. Its original
read-only regression suite is retained; tests use temporary roots and a curl
tripwire.

## Validation and rollout

Tests must use isolated roots, fake node/tmux processes, private fixture state
and no real service-manager actions or external messages. The original Python
concurrency/budget tests are retained and expanded for malformed state and exact
health targets. The real shell launcher tests cover denial after two failures,
preflight failure preserving the old pane, inherited ownership and pane mode.
TypeScript tests execute the actual backend-specific recovery functions.

This work is isolated from the production checkout and from the unrelated
Claude settings and voice edits. Those edits remain preserved in private
backups and must be reconciled separately before the normal updater can run.
A green build/test result is not deployment or proof of live model instruction
loading. Use the approved PR/review/release and update.sh flow only after its
preflight passes. No auto-stash, production hook override or manual production
build is part of this compatibility change.

Execution owner: Codex. Approving owner: MAG Attila. No deployment deadline has
been accepted; completion requires the recorded checks and runtime evidence.
