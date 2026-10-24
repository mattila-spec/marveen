# Shared shell client for the persistent main-channel recovery budget.
# Source only after read-only diagnostic modes have exited.
self_healing_claim() {
  SELF_HEALING_GATE="$INSTALL_DIR/scripts/self-healing-attempt-gate.py"
  SELF_HEALING_ACTOR="$1"
  SELF_HEALING_ATTEMPT_ID=""
  SELF_HEALING_OWNED=0
  SELF_HEALING_FINISHED=0
  local reply
  if [ -n "${MARVEEN_SELF_HEALING_ATTEMPT_ID:-}" ] || [ "${MARVEEN_SELF_HEALING_GATE_MANAGED:-}" = systemd-supervisor ]; then
    reply="$(python3 "$SELF_HEALING_GATE" status main-channels)" || return 73
    SELF_HEALING_ATTEMPT_ID="$(printf '%s' "$reply" | python3 -c '
import json, os, sys, time
d = json.load(sys.stdin); a = d.get("active") or {}
expected = os.environ.get("MARVEEN_SELF_HEALING_ATTEMPT_ID")
managed = os.environ.get("MARVEEN_SELF_HEALING_GATE_MANAGED") == "systemd-supervisor"
age = time.time() - float(a.get("started_at", 0))
if d.get("blocked") or int(d.get("failures", 0)) >= 2 or not (0 <= age < int(os.environ.get("MARVEEN_SELF_HEALING_ACTIVE_SECONDS", "420"))): sys.exit(73)
if (expected and a.get("id") != expected) or (not expected and managed and a.get("actor") != "systemd-supervisor"): sys.exit(73)
print(a.get("id", ""))
')" || return 73
  else
    reply="$(python3 "$SELF_HEALING_GATE" claim main-channels "$SELF_HEALING_ACTOR")" || return 73
    SELF_HEALING_ATTEMPT_ID="$(printf '%s' "$reply" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(73) if d.get("allowed") is not True else None; print(d["attempt_id"])')" || return 73
    SELF_HEALING_OWNED=1
  fi
  [ -n "$SELF_HEALING_ATTEMPT_ID" ] || return 73
}
self_healing_abort() {
  if [ "${SELF_HEALING_OWNED:-0}" = 1 ] && [ "${SELF_HEALING_FINISHED:-0}" = 0 ]; then
    python3 "$SELF_HEALING_GATE" fail main-channels "$SELF_HEALING_ATTEMPT_ID" "${1:-launcher exited before verified recovery}" >/dev/null 2>&1 || true
    SELF_HEALING_FINISHED=1
  fi
}
self_healing_watch() {
  if [ "${SELF_HEALING_OWNED:-0}" = 1 ]; then
    nohup python3 "$SELF_HEALING_GATE" watch main-channels "$SELF_HEALING_ATTEMPT_ID" "$1" </dev/null >/dev/null 2>&1 &
    SELF_HEALING_FINISHED=1
  fi
}
self_healing_resolve() {
  if [ "${SELF_HEALING_OWNED:-0}" = 1 ]; then
    python3 "$SELF_HEALING_GATE" resolve main-channels "$SELF_HEALING_ATTEMPT_ID" "$1" >/dev/null || return 1
    SELF_HEALING_FINISHED=1
  fi
}
