#!/bin/bash
# Regression tests for the read-only disk-space guard.
set -u

PASS=0; FAIL=0
TMPBASE="$(mktemp -d /tmp/dsg-test-XXXXXX)"
trap 'rm -rf "$TMPBASE"' EXIT
INSTALL_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
GUARD="$INSTALL_DIR/scripts/disk-space-guard.sh"
FAKEBIN="$TMPBASE/bin"
mkdir -p "$FAKEBIN"
touch_aged() { touch -t "$(python3 -c 'import time; print(time.strftime("%Y%m%d%H%M", time.localtime(time.time()-7200)))')" "$@"; }
pass() { PASS=$((PASS + 1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL: $1"; }
cat > "$FAKEBIN/curl" <<'SH'
#!/bin/sh
echo called >> "$FAKE_CURL_LOG"
exit 99
SH
chmod +x "$FAKEBIN/curl"
export PATH="$FAKEBIN:$PATH"
export FAKE_CURL_LOG="$TMPBASE/curl.log"

run_guard() {
  DISK_GUARD_USAGE_OVERRIDE="$1" \
  DISK_GUARD_SCRATCH_DIR="$2" \
  DISK_GUARD_STATE_DIR="$3" \
  DISK_GUARD_REAP_MIN_AGE_MIN="${4:-30}" \
    bash "$GUARD" 2>&1
}

echo "disk-space-guard read-only regression tests"
SCR="$TMPBASE/scratch"; ST="$TMPBASE/state"; mkdir -p "$SCR" "$ST"
touch_aged "$SCR/health_old.bin"
touch "$SCR/health_fresh.bin" "$SCR/unknown.bin"
OUT="$(run_guard 50 "$SCR" "$ST")"
[ -z "$OUT" ] && pass "below threshold is quiet" || fail "below threshold emitted output"
[ -e "$SCR/health_old.bin" ] && [ -e "$SCR/health_fresh.bin" ] && [ -e "$SCR/unknown.bin" ] && pass "below threshold leaves all files unchanged" || fail "below threshold changed files"

OUT="$(run_guard 92 "$SCR" "$ST")"
[ -e "$SCR/health_old.bin" ] && pass "old allowlisted file is never deleted" || fail "old allowlisted file was deleted"
[ -e "$SCR/health_fresh.bin" ] && [ -e "$SCR/unknown.bin" ] && pass "fresh and unclassified files are preserved" || fail "fresh or unclassified file changed"
printf '%s' "$OUT" | grep -q "CANDIDATE.*low-risk candidate.*health_old.bin" && pass "old allowlisted scratch is listed with risk class" || fail "candidate risk listing missing"
printf '%s' "$OUT" | grep -q "post-check disk 92% (no files changed)" && pass "post-check does not imply recovered capacity" || fail "post-check evidence missing"

OUT="$(run_guard 96 "$SCR" "$ST")"
printf '%s' "$OUT" | grep -q "ALERT local-only" && pass "critical capacity emits local escalation" || fail "local escalation missing"
! printf '%s' "$OUT" | grep -q "ALERT_DRYRUN" && pass "legacy hook cannot mask external alert path" || fail "unexpected dry-run output"
[ -f "$ST/.disk-guard-alerted" ] && pass "local alert cooldown is recorded" || fail "cooldown missing"
OUT2="$(run_guard 96 "$SCR" "$ST")"
printf '%s' "$OUT2" | grep -q "within alert cooldown" && pass "cooldown suppresses repeated log alerts" || fail "cooldown failed"
[ ! -e "$FAKE_CURL_LOG" ] && pass "no external notification command was invoked" || fail "curl was invoked"

OUT="$(run_guard invalid "$SCR" "$ST")"
printf '%s' "$OUT" | grep -q "could not read disk usage" && pass "invalid measurement fails closed" || fail "invalid measurement not handled"
[ -e "$SCR/health_old.bin" ] && pass "invalid measurement leaves files unchanged" || fail "invalid measurement changed files"

mkdir -p "$SCR/health_active"
touch "$SCR/health_active/recent.part"
touch_aged "$SCR/health_active"
OUT="$(run_guard 92 "$SCR" "$ST")"
printf '%s' "$OUT" | grep -q "directory contains a recent file" && pass "directory with recent child is risk-classified for review" || fail "active directory classification missing"
[ -e "$SCR/health_active/recent.part" ] && pass "active directory data is preserved" || fail "active directory data changed"

if grep -Eq 'rm[[:space:]]+-rf|send_telegram_message|curl[[:space:]]' "$GUARD"; then
  fail "production guard source has destructive or outbound command"
else
  pass "production guard source contains no delete or outbound-send path"
fi

echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
