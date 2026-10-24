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
