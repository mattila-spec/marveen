#!/bin/bash
# Disk-space guard for the host (systemd --user timer, every minute).
#
# Incident it fixes (2026-06-03 dawn): the root filesystem filled to 100% from a
# 2.2G orphaned /tmp/health_* Apple Health export (the apple-health skill's
# scratch cleanup didn't run). A full root wedged the main session in a /mcp
# modal and every disk-touching watchdog gave false signals. This guard is the
# independent net: it measures capacity and reports possible scratch candidates.
# It never deletes files and never sends an automatic external notification.
#
# Determinism + safety:
#   - Thresholds are constants at the top.
#   - Candidate reporting is restricted to an explicit allowlist of scratch
#     globs AND an age guard. Reporting is not authorization to delete.
#   - Critical alerts are local-only; external sending requires separate approval.
#   - Every stamp/log write is best-effort: under ENOSPC a failed write must not
#     wedge or crash the guard (that is the whole point).
#
# Test hooks (env, used only by scripts/__tests__/disk-space-guard.test.sh):
#   DISK_GUARD_USAGE_OVERRIDE   - use this usage% instead of df (integer)
#   DISK_GUARD_SCRATCH_DIR      - candidate scan base dir (default /tmp)
#   DISK_GUARD_STATE_DIR        - cooldown-stamp dir (default <install>/store)
#   DISK_GUARD_REAP_MIN_AGE_MIN - override the reap age guard (minutes)
#   DISK_GUARD_ALERT_DRYRUN     - legacy test hook; all alerts are local-only

set -u

# --- thresholds (tunable constants) ---
DISK_PATH="/"
REAP_THRESHOLD=90        # >= this %: inventory safe scratch candidates
ALERT_THRESHOLD=95       # >= this %: emit a local alert for manual review
REAP_MIN_AGE_MIN="${DISK_GUARD_REAP_MIN_AGE_MIN:-30}"   # only reap orphans older than this
# Numeric-validate the age guard BEFORE use: a malformed env (e.g. "abc", "-1")
# OR literal 0 must NOT degrade into "reap everything" (-mmin +0 matches an
# in-progress export). Fall back to a very conservative day.
case "$REAP_MIN_AGE_MIN" in (''|0|*[!0-9]*) REAP_MIN_AGE_MIN=1440;; esac
ALERT_COOLDOWN=3600      # at most one disk-full alert per hour

# Explicit allowlist of scratch globs reported under SCRATCH_DIR (maxdepth 1).
# Space-separated env override DISK_GUARD_REAP_GLOBS; the default targets the
# apple-health analysis scratch that caused the original incident. Extend
# deliberately. An allowlist match never permits automatic deletion.
if [ -n "${DISK_GUARD_REAP_GLOBS:-}" ]; then
  read -r -a REAP_GLOBS <<< "$DISK_GUARD_REAP_GLOBS"
else
  REAP_GLOBS=("health_*")
fi

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRATCH_DIR="${DISK_GUARD_SCRATCH_DIR:-/tmp}"
STATE_DIR="${DISK_GUARD_STATE_DIR:-$INSTALL_DIR/store}"
ALERT_STAMP="$STATE_DIR/.disk-guard-alerted"
# #915: main channel state is install-scoped once migrated; the legacy shared
# path only serves unmigrated installs.
TG_CHAN_DIR="${TELEGRAM_STATE_DIR:-}"
if [ -z "$TG_CHAN_DIR" ]; then
  TG_CHAN_DIR="$INSTALL_DIR/.claude/channels/telegram"
  [ -f "$TG_CHAN_DIR/.env" ] || TG_CHAN_DIR="$HOME/.claude/channels/telegram"
fi
TG_ENV="$TG_CHAN_DIR/.env"
LOG_TAG="disk-space-guard"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [$LOG_TAG] $*" || true; }

# Current usage% of DISK_PATH (0-100), or the test override.
disk_usage() {
  if [ -n "${DISK_GUARD_USAGE_OVERRIDE:-}" ]; then
    echo "$DISK_GUARD_USAGE_OVERRIDE"; return
  fi
  df -P "$DISK_PATH" 2>/dev/null | awk 'NR==2 {gsub("%","",$5); print $5}'
}

# Read-only inventory of old allowlisted scratch candidates. Candidate paths
# are quoted in the log and categorized; no file content is opened or changed.
list_scratch_candidates() {
  local glob path real size risk
  [ -d "$SCRATCH_DIR" ] || return 0
  [ -L "$SCRATCH_DIR" ] && { log "candidate scan skipped: scratch path is a symlink"; return 0; }
  real="$(realpath "$SCRATCH_DIR" 2>/dev/null \
        || readlink -f "$SCRATCH_DIR" 2>/dev/null \
        || (cd "$SCRATCH_DIR" 2>/dev/null && pwd -P))"
  case "$real/" in
    /tmp/*|/private/tmp/*|"${XDG_RUNTIME_DIR:-/nonexistent-xdg}"/*) : ;;
    *) log "candidate scan skipped: scratch path is outside approved temp roots"; return 0 ;;
  esac
  for glob in "${REAP_GLOBS[@]}"; do
    while IFS= read -r -d '' path; do
      case "$path" in "$SCRATCH_DIR"/*) : ;; *) continue ;; esac
      if [ -d "$path" ] && [ ! -L "$path" ] && find "$path" -type f -mmin "-$REAP_MIN_AGE_MIN" -print -quit 2>/dev/null | grep -q .; then
        risk="review: directory contains a recent file"
      else
        risk="low-risk candidate: old allowlisted temp data; approval still required"
      fi
      size="$(du -sk -- "$path" 2>/dev/null | awk '{print $1}')"
      log "CANDIDATE risk='$risk' size_kb=${size:-unknown} path=$(printf '%q' "$path")"
    done < <(find "$SCRATCH_DIR" -maxdepth 1 -name "$glob" -mmin "+$REAP_MIN_AGE_MIN" -print0 2>/dev/null)
  done
}

# Local-only alert. External notification requires separate authorization.
alert_owner() {
  log "ALERT local-only: $1"
  return 0
}

main() {
  local usage now last
  # Ensure the state dir exists UP FRONT so the cooldown stamp write below always
  # succeeds. Otherwise (missing STATE_DIR) the stamp never persists, `last` stays
  # 0 every tick, and a stuck-full disk re-alerts up to 60x/hour.
  mkdir -p "$STATE_DIR" 2>/dev/null || true
  usage="$(disk_usage)"
  case "$usage" in (''|*[!0-9]*) log "could not read disk usage (got '$usage') -- no-op"; return 0;; esac

  if [ "$usage" -lt "$REAP_THRESHOLD" ]; then
    return 0   # plenty of room
  fi

  log "disk ${usage}% >= ${REAP_THRESHOLD}% -- read-only candidate scan under $SCRATCH_DIR"
  list_scratch_candidates
  usage="$(disk_usage)"
  log "post-check disk ${usage}% (no files changed)"

  if [ "$usage" -ge "$ALERT_THRESHOLD" ]; then
    # Cooldown so a stuck-full disk alerts at most once/hour (best-effort stamp).
    now="$(date +%s)"
    last=0; [ -f "$ALERT_STAMP" ] && last="$(cat "$ALERT_STAMP" 2>/dev/null || echo 0)"
    case "$last" in (''|*[!0-9]*) last=0;; esac
    if [ $(( now - last )) -ge "$ALERT_COOLDOWN" ]; then
      alert_owner "${DISK_PATH} is at ${usage}% after read-only scan. Manual review required; no files were changed."
      echo "$now" > "$ALERT_STAMP" 2>/dev/null || true
    else
      log "disk ${usage}% critical but within alert cooldown ($(( now - last ))s) -- skip alert"
    fi
  fi
}

main "$@"
exit 0
