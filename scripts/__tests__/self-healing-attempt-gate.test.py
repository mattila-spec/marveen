#!/usr/bin/env python3
"""Regression tests for the cross-process, per-incident recovery gate."""

import concurrent.futures
import importlib.util
import socket
import time
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "self-healing-attempt-gate.py"


def invoke(state_file, *args, **extra_env):
    env = os.environ.copy()
    env.update(MARVEEN_SELF_HEALING_STATE_FILE=str(state_file), **extra_env)
    return subprocess.run([sys.executable, str(GATE), *args], text=True,
                          capture_output=True, env=env, timeout=10)


def result(proc):
    return json.loads(proc.stdout or proc.stderr)


def main():
    with tempfile.TemporaryDirectory(prefix="healing-gate-test-") as tmp:
        state = Path(tmp) / "state.json"

        # Concurrent actors share one lock and cannot both own an incident.
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            claims = list(pool.map(lambda i: invoke(state, "claim", "main-channels", f"race-{i}"), range(8)))
        allowed = [result(p) for p in claims if p.returncode == 0]
        denied = [result(p) for p in claims if p.returncode != 0]
        assert len(allowed) == 1, f"expected one active claim, got {len(allowed)}"
        assert len(denied) == 7
        print("PASS: concurrent actors serialize on one active attempt")

        first = allowed[0]
        failed = invoke(state, "fail", "main-channels", first["attempt_id"], "fixture health check failed")
        assert failed.returncode == 0 and result(failed)["failures"] == 1

        # A different recovery actor may take attempt two after failure one.
        second = invoke(state, "claim", "main-channels", "systemd-supervisor")
        assert second.returncode == 0
        failed = invoke(state, "fail", "main-channels", result(second)["attempt_id"], "second fixture health failure")
        assert failed.returncode == 0 and result(failed)["blocked"] is True

        # A third, different component cannot bypass the incident budget.
        third = invoke(state, "claim", "main-channels", "channel-monitor")
        assert third.returncode == 3 and result(third)["failures"] == 2
        print("PASS: two failures across different actors block the third recovery")

        # Automatic retries stay blocked until an explicit human-recorded reset.
        denied = invoke(state, "claim", "main-channels", "stuck-modal-guard")
        assert denied.returncode == 3
        assert invoke(state, "manual-reset", "main-channels").returncode == 2
        reset = invoke(state, "manual-reset", "main-channels", "operator inspected logs and approved retry")
        assert reset.returncode == 0 and result(reset)["failures"] == 0

        # Independent incidents have independent budgets.
        other = invoke(state, "claim", "dashboard", "dashboard-supervisor")
        assert other.returncode == 0
        print("PASS: budgets are scoped per incident key")

        recovered_state = Path(tmp) / "recovered.json"
        attempt1 = invoke(recovered_state, "claim", "main-channels", "watchdog")
        invoke(recovered_state, "fail", "main-channels", result(attempt1)["attempt_id"], "failed")
        attempt2 = invoke(recovered_state, "claim", "main-channels", "monitor")
        healed = invoke(recovered_state, "resolve", "main-channels", result(attempt2)["attempt_id"],
                        "verified session and fresh keepalive")
        assert healed.returncode == 0 and result(healed)["failures"] == 0
        assert invoke(recovered_state, "claim", "main-channels", "future-incident").returncode == 0
        print("PASS: verified recovery resets only its incident budget")

        # Stale unverified ownership fails closed by consuming one failure.
        stale_state = Path(tmp) / "stale.json"
        stale = invoke(stale_state, "claim", "main-channels", "dead-owner",
                       MARVEEN_SELF_HEALING_ACTIVE_SECONDS="0")
        assert stale.returncode == 0
        next_claim = invoke(stale_state, "claim", "main-channels", "next-actor",
                            MARVEEN_SELF_HEALING_ACTIVE_SECONDS="0")
        assert next_claim.returncode == 0 and result(next_claim)["failures"] == 1
        print("PASS: stale unverified recovery is charged before another attempt")

        # Invalid persisted counters/ownership must not become a fresh budget.
        for broken in ["not json", json.dumps({"version": 1, "incidents": {"main-channels": {"failures": -1, "active": None, "blocked": False}}}), json.dumps({"version": 1, "incidents": {"main-channels": {"failures": 0, "active": "invalid", "blocked": False}}})]:
            bad = Path(tmp) / "invalid.json"
            bad.write_text(broken)
            refused = invoke(bad, "claim", "main-channels", "monitor")
            assert refused.returncode == 2 and result(refused)["allowed"] is False
            assert bad.read_text() == broken
        print("PASS: malformed persisted state fails closed without rewriting evidence")

        # A watcher must use an exact tmux session selector, not a prefix.
        fake_tmux = Path(tmp) / "tmux"
        fake_tmux.write_text("#!/usr/bin/env python3\nimport json,sys,os\nfrom pathlib import Path\nPath(os.environ['TMUX_CAPTURE']).write_text(json.dumps(sys.argv[1:]))\nsys.exit(0 if sys.argv[1:]==['has-session','-t','=fixture-channels:'] else 1)\n")
        fake_tmux.chmod(0o700)
        watched = Path(tmp) / "watched.json"
        claimed = result(invoke(watched, "claim", "main-channels", "watcher"))
        keepalive = Path(tmp) / "keepalive"
        keepalive.touch()
        capture = Path(tmp) / "tmux.json"
        verified = invoke(watched, "watch", "main-channels", claimed["attempt_id"], "fixture-channels", TMUX_BIN=str(fake_tmux), TMUX_CAPTURE=str(capture), MARVEEN_CHANNEL_KEEPALIVE_FILE=str(keepalive), MARVEEN_SELF_HEALING_WATCH_SECONDS="2", MARVEEN_SELF_HEALING_STABLE_SECONDS="0", MARVEEN_SELF_HEALING_POLL_SECONDS="0.01")
        assert verified.returncode == 0 and result(verified)["result"] == "resolved"
        assert json.loads(capture.read_text()) == ["has-session", "-t", "=fixture-channels:"]
        print("PASS: exact tmux session and fresh keepalive verify recovery")

        # Codex has no Claude keepalive: exercise a real local Unix listener,
        # current test PID, fresh status and the actual watcher subprocess.
        install = Path(tmp) / "codex-install"
        codex_store = install / "store" / "codex"
        codex_store.mkdir(parents=True)
        codex_state = Path(tmp) / "codex-attempt.json"
        claim = result(invoke(codex_state, "claim", "main-channels", "codex-watch"))
        status_path = codex_store / "status.json"
        status_path.write_text(json.dumps({"pid": os.getpid(), "busy": False}))
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(codex_store / "channel.sock"))
            listener.listen(8)
            verified = invoke(codex_state, "watch", "main-channels", claim["attempt_id"], "fixture-channels",
                TMUX_BIN=str(fake_tmux), TMUX_CAPTURE=str(capture), MARVEEN_INSTALL_DIR=str(install),
                MARVEEN_AGENT_BACKEND="codex", MARVEEN_SELF_HEALING_WATCH_SECONDS="2",
                MARVEEN_SELF_HEALING_STABLE_SECONDS="0", MARVEEN_SELF_HEALING_POLL_SECONDS="0.01")
            assert verified.returncode == 0 and result(verified)["result"] == "resolved"
            spec = importlib.util.spec_from_file_location("gate_fixture", GATE)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            assert module.codex_health(install, time.time() - 2)
            assert not module.codex_health(install, time.time() + 1), "old snapshot must not prove a new launch"
            status_path.write_text(json.dumps({"pid": 0, "busy": False}))
            assert not module.codex_health(install, 0), "invalid PID must fail closed"
            status_path.write_text(json.dumps({"pid": os.getpid(), "busy": False}))
        assert not module.codex_health(install, 0), "stale socket must not prove a healthy process"
        assert not (install / "store" / ".channel-keepalive").exists()
        print("PASS: Codex recovery verifies live PID and local socket without a Claude heartbeat; stale evidence fails closed")



if __name__ == "__main__":
    main()
