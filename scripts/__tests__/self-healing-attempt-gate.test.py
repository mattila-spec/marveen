#!/usr/bin/env python3
"""Regression tests for the cross-process, per-incident recovery gate."""

import concurrent.futures
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


if __name__ == "__main__":
    main()
