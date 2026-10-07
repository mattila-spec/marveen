#!/usr/bin/env python3
"""Shared, durable attempt gate for automatic recovery of a service incident.

All callers for one affected service use the same incident key. A claimed
attempt remains active until verified healthy or explicitly failed. The gate
fails closed on stale or malformed state and serializes concurrent callers.
"""

import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
STATE = Path(os.environ.get(
    "MARVEEN_SELF_HEALING_STATE_FILE",
    str(ROOT / "store" / ".self-healing-attempts.json"),
))
MAX_FAILURES = 2
MAX_ACTIVE_SECONDS = int(os.environ.get("MARVEEN_SELF_HEALING_ACTIVE_SECONDS", "420"))


def empty_state():
    return {"version": 1, "incidents": {}}


def read_state():
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("incidents"), dict):
            raise ValueError("unsupported state format")
        return data
    except FileNotFoundError:
        return empty_state()
    except Exception as exc:
        raise RuntimeError(f"state unreadable; refusing recovery: {exc}") from exc


def write_state(data):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".self-healing-attempts-", dir=STATE.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, sort_keys=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, STATE)
        os.chmod(STATE, 0o600)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def with_state(fn):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = STATE.with_suffix(STATE.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        data = read_state()
        result, dirty = fn(data)
        if dirty:
            write_state(data)
        return result


def incident_key(raw):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", raw):
        raise ValueError("invalid incident key")
    return raw


def item_for(data, key):
    return data["incidents"].setdefault(key, {
        "failures": 0, "active": None, "blocked": False,
        "last_failure": None, "last_resolved": None,
    })


def claim(key, actor):
    key = incident_key(key)
    if not actor or len(actor) > 100:
        raise ValueError("invalid actor")
    now = time.time()

    def action(data):
        item = item_for(data, key)
        active = item.get("active")
        changed = False
        if active and now - float(active.get("started_at", now)) >= MAX_ACTIVE_SECONDS:
            item["failures"] = int(item.get("failures", 0)) + 1
            item["last_failure"] = {
                "at": now,
                "actor": active.get("actor", "unknown"),
                "reason": "attempt expired without verified recovery",
            }
            item["active"] = None
            item["blocked"] = item["failures"] >= MAX_FAILURES
            active = None
            changed = True
        if item.get("blocked") or int(item.get("failures", 0)) >= MAX_FAILURES:
            item["blocked"] = True
            return ({"allowed": False, "reason": "two failed attempts; STOP and escalate",
                     "failures": int(item.get("failures", 0)), "incident": key}, True)
        if active:
            return ({"allowed": False, "reason": "another recovery attempt is active",
                     "failures": int(item.get("failures", 0)), "incident": key}, changed)
        token = uuid.uuid4().hex
        item["active"] = {"id": token, "actor": actor, "started_at": now}
        item["blocked"] = False
        return ({"allowed": True, "attempt_id": token, "failures": int(item.get("failures", 0)),
                 "incident": key, "actor": actor}, True)

    return with_state(action)


def finish(key, token, *, success, evidence, actor=None):
    key = incident_key(key)
    if not evidence.strip():
        raise ValueError("evidence is required")
    now = time.time()

    def action(data):
        item = item_for(data, key)
        active = item.get("active")
        if not active or active.get("id") != token or (actor and active.get("actor") != actor):
            return ({"ok": False, "reason": "attempt token does not own the active incident",
                     "incident": key}, False)
        if success:
            item["failures"] = 0
            item["blocked"] = False
            item["last_resolved"] = {"at": now, "actor": active.get("actor"), "evidence": evidence[:1000]}
        else:
            item["failures"] = int(item.get("failures", 0)) + 1
            item["last_failure"] = {"at": now, "actor": active.get("actor"), "reason": evidence[:1000]}
            item["blocked"] = item["failures"] >= MAX_FAILURES
        item["active"] = None
        return ({"ok": True, "incident": key, "failures": int(item["failures"]),
                 "blocked": bool(item["blocked"]), "result": "resolved" if success else "failed"}, True)

    return with_state(action)


def current(key):
    key = incident_key(key)
    return with_state(lambda data: ({"incident": key, **item_for(data, key)}, False))


def watch_active(key, actor, session):
    state = current(key)
    active = state.get("active")
    if not active or active.get("actor") != actor:
        return {"ok": True, "reason": "no active attempt owned by actor", "incident": key}
    if session == "-":
        main_agent = "marveen"
        env_file = ROOT / ".env"
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("MAIN_AGENT_ID="):
                    main_agent = line.split("=", 1)[1].strip() or main_agent
                    break
        except OSError:
            pass
        session = main_agent + "-channels"
    return watch_health(key, active["id"], session)


def manual_reset(key, evidence):
    key = incident_key(key)
    if not evidence.strip():
        raise ValueError("manual operator evidence is required")
    now = time.time()

    def action(data):
        item = item_for(data, key)
        if item.get("active"):
            return ({"ok": False, "reason": "active attempt must be resolved or failed first", "incident": key}, False)
        item["failures"] = 0
        item["blocked"] = False
        item["last_resolved"] = {"at": now, "actor": "manual-operator", "evidence": evidence[:1000]}
        return ({"ok": True, "incident": key, "failures": 0, "blocked": False}, True)

    return with_state(action)


def watch_health(key, token, session):
    key = incident_key(key)
    timeout = int(os.environ.get("MARVEEN_SELF_HEALING_WATCH_SECONDS", "300"))
    stable_needed = int(os.environ.get("MARVEEN_SELF_HEALING_STABLE_SECONDS", "30"))
    poll = float(os.environ.get("MARVEEN_SELF_HEALING_POLL_SECONDS", "5"))
    install = Path(os.environ.get("MARVEEN_INSTALL_DIR", str(ROOT)))
    keepalive = Path(os.environ.get("MARVEEN_CHANNEL_KEEPALIVE_FILE", str(install / "store" / ".channel-keepalive")))
    active = current(key).get("active")
    if not active or active.get("id") != token:
        return {"ok": True, "reason": "attempt already completed or superseded", "incident": key}
    attempt_started = float(active.get("started_at", time.time()))
    stable_since = None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pane_ok = False
        try:
            pane_ok = subprocess.run(
                [os.environ.get("TMUX_BIN", "tmux"), "has-session", "-t", session],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3,
            ).returncode == 0
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            keepalive_mtime = keepalive.stat().st_mtime if keepalive.is_file() else 0
            keepalive_ok = keepalive_mtime >= attempt_started and time.time() - keepalive_mtime <= 300
        except OSError:
            keepalive_ok = False
        if pane_ok and keepalive_ok:
            if stable_since is None:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= stable_needed:
                return finish(key, token, success=True,
                              evidence=f"tmux session {session} present and channel keepalive fresh for {stable_needed}s")
        else:
            stable_since = None
        time.sleep(poll)
    return finish(key, token, success=False,
                  evidence=f"health check did not pass within {timeout}s for {session}")


def main(argv):
    if len(argv) < 3:
        raise ValueError("usage: self-healing-attempt-gate.py claim|status|resolve|fail|fail-active|watch INCIDENT ...")
    command, key = argv[1], argv[2]
    if command == "claim" and len(argv) == 4:
        result = claim(key, argv[3])
    elif command == "status" and len(argv) == 3:
        result = current(key)
    elif command in ("resolve", "fail") and len(argv) >= 5:
        result = finish(key, argv[3], success=command == "resolve", evidence=" ".join(argv[4:]))
    elif command == "fail-active" and len(argv) >= 5:
        item = current(key)
        active = item.get("active")
        if active and active.get("actor") == argv[3]:
            result = finish(key, active["id"], success=False, evidence=" ".join(argv[4:]), actor=argv[3])
        else:
            result = {"ok": True, "reason": "no active attempt owned by actor", "incident": key}
    elif command == "watch" and len(argv) == 5:
        result = watch_health(key, argv[3], argv[4])
    elif command == "watch-active" and len(argv) in (4, 5):
        result = watch_active(key, argv[3], argv[4] if len(argv) == 5 else "-")
    elif command == "manual-reset" and len(argv) >= 4:
        result = manual_reset(key, " ".join(argv[3:]))
    else:
        raise ValueError("invalid command arguments")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if command == "claim" and not result.get("allowed"):
        return 3
    if command in ("resolve", "fail") and not result.get("ok"):
        return 4
    if command in ("watch", "watch-active") and not result.get("ok"):
        return 5
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:
        print(json.dumps({"allowed": False, "ok": False, "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
