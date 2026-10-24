# Canonical owner operating rules

`AGENTS.md` is the approved, versioned source. This change preserves its exact
approved wording. Both Codex main-channel lanes read it before persona files;
workers read it from the requested cwd before opening an app-server. Missing,
unreadable or empty rules fail closed. Smoke/bridge fixtures never use real
channels.

For Claude-backed agents, `ensureOwnerOperatingRulesSection` synchronizes one
managed block at launch, using the project root for the main persona and the
agent directory for subagents. Existing blocks refresh when the canonical source
changes; duplicate complete blocks collapse to one; malformed markers fail closed.
The main dashboard startup synchronizes only outside WEB_ONLY mode. Newly created
agents receive the block before their first launch reads their generated persona.
The optional path parameters exist for isolated filesystem tests.

## Validation and rollout

The owner-rules regression suite exercises the actual channel builder, a real
worker subprocess with a fake local app-server, managed prompt updates, missing
inputs, main and subagent paths, and the actual WEB_ONLY startup conditional.
No live model API or production restart is used by those tests.

Prerequisite: merge the separately reviewed Codex integration into develop.
Then review this owner-rules change and use the approved release/update.sh flow.
The production checkout still has unrelated tracked edits: a dirty-tree preflight
must stop rollout without AUTO_STASH, reset, or commit-hook overrides.
Runtime acceptance is pending until an approved release is actually deployed;
unit/build success is not evidence of running agent prompt loading.

## Source-only follow-up (2026-10-24)

The isolated source now uses the complete approved rules 1?5, copied byte for
byte from the owner's canonical AGENTS.md. The existing regression fixtures now
exercise that complete source, including the existing economic and procurement
agents and newly scaffolded agents. Rule text and outgoing-message approvals
are unchanged. No deadline has been accepted.

Standalone Claude channel cold starts, retries, channel watchdog recovery,
stuck-modal recovery, agent watchdog starts, and dashboard main-pane recovery
now call the existing synchronizer before launching the replacement process.
The shell gate uses the compiled synchronizer through scripts/sync-owner-rules.mjs;
a missing build or canonical source aborts launch. Diagnostic script modes remain
read-only. This gate does not reload an already running model context.

The initial follow-up was source-only. MAG Attila subsequently authorized review,
release decisions and controlled production validation on 2026-10-24. Existing
review, release and dirty-tree guards still apply. Production prompt files were
inspected read-only; file contents are not proof that a running session consumed
those contents. A nested malformed managed block now fails closed as well.
