#!/usr/bin/env python3
"""Run destructive-looking recovery drills only against disposable local fixtures.

The output distinguishes real component execution from policy-only simulation.
No production process, database, backup, or mount is a test target.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
import time

ROOT = Path(__file__).resolve().parents[2]
RESULTS = []


def record(name, kind, checks, evidence):
    RESULTS.append({"scenario": name, "kind": kind, "checks": checks, "evidence": evidence})


def run(command, *, cwd=None, env=None):
    return subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=30)


with tempfile.TemporaryDirectory(prefix="marveen-self-healing-drill-", dir="/tmp") as td:
    base = Path(td)
    # 1. Execute the shipped watchdog with an isolated install and fake executables.
    wd = base / "watchdog"
    (wd / "scripts").mkdir(parents=True)
    (wd / "store").mkdir()
    shutil.copy2(ROOT / "scripts/channel-watchdog.sh", wd / "scripts/channel-watchdog.sh")
    shutil.copy2(ROOT / "scripts/self-healing-attempt-gate.py", wd / "scripts/self-healing-attempt-gate.py")
    (wd / ".env").write_text("MAIN_AGENT_ID=drill\n", encoding="utf-8")
    fakebin = wd / "bin"
    fakebin.mkdir()
    tmux_log = wd / "tmux-calls"
    (fakebin / "tmux").write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$1\" >> \"$DRILL_TMUX_LOG\"\n"
        "if [ \"$1\" = has-session ]; then [ \"${DRILL_SESSION_UP:-0}\" = 1 ]; else exit 0; fi\n",
        encoding="utf-8",
    )
    (fakebin / "claude").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for p in fakebin.iterdir():
        p.chmod(0o700)
    env = os.environ.copy()
    env.update(PATH=str(fakebin) + os.pathsep + env.get("PATH", ""), DRILL_TMUX_LOG=str(tmux_log),
               MARVEEN_SELF_HEALING_STATE_FILE=str(wd / "store/.self-healing-attempts.json"),
               MARVEEN_SELF_HEALING_WATCH_SECONDS="1", MARVEEN_SELF_HEALING_POLL_SECONDS="0.05",
               MARVEEN_SELF_HEALING_STABLE_SECONDS="0", MARVEEN_SELF_HEALING_ACTIVE_SECONDS="2")
    down = run(["bash", str(wd / "scripts/channel-watchdog.sh")], env=env)
    down_calls = tmux_log.read_text().splitlines()
    ka = wd / "store/.channel-keepalive"
    ka.touch()
    old = datetime.now(timezone.utc).timestamp() - 3600
    os.utime(ka, (old, old))
    env["DRILL_SESSION_UP"] = "1"
    outputs = []
    for n in range(3):
        if n:
            stamp = wd / "store/.channel-last-respawn"
            if stamp.exists():
                os.utime(stamp, (old, old))
        r = run(["bash", str(wd / "scripts/channel-watchdog.sh")], env=env)
        outputs.append(r.stdout)
        if n < 2:
            time.sleep(1.3)
    all_calls = tmux_log.read_text().splitlines()
    respawns = sum(x == "respawn-pane" for x in all_calls)
    record("service_down", "actual channel-watchdog.sh with fake tmux/claude", {
        "missing_session_no_respawn": down.returncode == 0 and "no-op" in down.stdout and down_calls == ["has-session"],
        "stale_session_respawns": respawns,
        "two_attempt_stop_obeyed": respawns <= 2,
        "shared_gate_stops_third_actor_attempt": "STOP" in outputs[-1],
    }, {"missing_session_log": down.stdout.strip(), "stale_logs": [x.strip().splitlines()[-1] for x in outputs]})

    # 2. Exercise the actual disk guard against a fake df and disposable /tmp files.
    disk = base / "disk"
    disk.mkdir()
    scratch = disk / "scratch"
    scratch.mkdir()
    stale = scratch / "health_old"
    stale.write_text("disposable", encoding="utf-8")
    os.utime(stale, (old, old))
    fresh = scratch / "health_fresh"
    fresh.write_text("keep", encoding="utf-8")
    unrelated = scratch / "backup_keep"
    unrelated.write_text("keep", encoding="utf-8")
    dfbin = disk / "bin"
    dfbin.mkdir()
    (dfbin / "df").write_text(
        "#!/bin/sh\nprintf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'\n"
        f"if [ -e '{stale}' ]; then echo 'mock 100 96 4 96% /'; "
        "else echo 'mock 100 88 12 88% /'; fi\n",
        encoding="utf-8",
    )
    (dfbin / "df").chmod(0o700)
    denv = os.environ.copy()
    denv.update(PATH=str(dfbin) + os.pathsep + denv.get("PATH", ""),
                DISK_GUARD_SCRATCH_DIR=str(scratch), DISK_GUARD_STATE_DIR=str(disk / "state"),
                DISK_GUARD_ALERT_DRYRUN="1")
    d = run(["bash", str(ROOT / "scripts/disk-space-guard.sh")], env=denv)
    record("disk_full", "actual disk-space-guard.sh with fake df", {
        "detected_96_percent": "disk 96%" in d.stdout,
        "postcheck_no_mutation": "post-check disk 96% (no files changed)" in d.stdout,
        "old_allowlisted_scratch_preserved": stale.exists(),
        "fresh_and_unrelated_preserved": fresh.exists() and unrelated.exists(),
        "no_automatic_delete": stale.exists() and fresh.exists() and unrelated.exists(),
    }, {"guard_log": d.stdout.strip(), "exit_code": d.returncode})

    # 3/5. Synthetic release target. The operator, not update.sh, decides rollback.
    rel = base / "releases"
    rel.mkdir()
    good = rel / "good"
    bad = rel / "bad"
    good.write_text("healthy\naccount=7\n", encoding="utf-8")
    bad.write_text("HTTP 500\naccount=7\n", encoding="utf-8")
    active = rel / "active"
    active.symlink_to(good)
    before = active.read_text()
    active.unlink()
    active.symlink_to(bad)
    broken = active.read_text()
    active.unlink()
    active.symlink_to(good)
    restored = active.read_text()
    record("bad_deploy", "synthetic release/rollback policy drill; update.sh not executed", {
        "bad_release_detected": "HTTP 500" in broken,
        "known_good_verified_before_change": "healthy" in before,
        "rollback_restored_health": "healthy" in restored,
        "data_consistent": "account=7" in before and "account=7" in restored,
    }, {"before_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "bad_sha256": hashlib.sha256(broken.encode()).hexdigest(),
        "restored_sha256": hashlib.sha256(restored.encode()).hexdigest()})

    # 4. Isolated SQLite connection failure with read-only recovery check.
    dbpath = base / "drill.sqlite"
    conn = sqlite3.connect(dbpath)
    conn.execute("CREATE TABLE sample (value TEXT)")
    conn.execute("INSERT INTO sample VALUES ('preserved')")
    conn.commit()
    initial = conn.execute("SELECT value FROM sample").fetchone()[0]
    conn.close()
    error = ""
    try:
        conn.execute("SELECT value FROM sample")
    except sqlite3.ProgrammingError as exc:
        error = str(exc)
    reopened = sqlite3.connect(dbpath)
    after = reopened.execute("SELECT value FROM sample").fetchone()[0]
    reopened.close()
    record("db_connection_lost", "synthetic SQLite fixture; Marveen DB runtime not executed", {
        "closed_connection_detected": "closed database" in error,
        "read_only_reopen_recovers": initial == after == "preserved",
        "data_preserved": dbpath.exists(),
    }, {"connection_error": error, "value_after_reopen": after})

    # 5. Missing rollback: no further modification of the broken release.
    missing = rel / "missing-good"
    current = bad.read_text()
    rollback_available = missing.exists()
    after_stop = bad.read_text()
    record("rollback_unavailable", "synthetic release policy drill", {
        "rollback_missing_proven": not rollback_available,
        "stopped_without_change": current == after_stop,
    }, {"known_good_path": str(missing), "exists": rollback_available})

    # 6. Preserve original test archive, corrupt a COPY, restore to empty target.
    payload = base / "payload.txt"
    payload.write_text("disposable restore data", encoding="utf-8")
    archive = base / "backup.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(payload, arcname="payload.txt")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    corrupt = base / "backup-corrupt.tar.gz"
    corrupt.write_bytes(archive.read_bytes()[:10])
    target = base / "restore-target"
    target.mkdir()
    restore_error = ""
    try:
        with tarfile.open(corrupt, "r:gz") as tf:
            tf.extractall(target, filter="data")
    except (tarfile.TarError, EOFError, OSError) as exc:
        restore_error = type(exc).__name__ + ": " + str(exc)
    record("backup_restore_fails", "synthetic archive/isolated restore target", {
        "backup_file_exists": corrupt.exists(),
        "restore_failure_detected": bool(restore_error),
        "original_preserved": hashlib.sha256(archive.read_bytes()).hexdigest() == archive_hash,
        "target_untouched": list(target.iterdir()) == [],
    }, {"original_sha256": archive_hash,
        "corrupt_sha256": hashlib.sha256(corrupt.read_bytes()).hexdigest(),
        "restore_error": restore_error})

    print(json.dumps({"timestamp_utc": datetime.now(timezone.utc).isoformat(),
                      "isolation": "TemporaryDirectory under /tmp; all contents removed on exit",
                      "results": RESULTS}, ensure_ascii=False, indent=2))
