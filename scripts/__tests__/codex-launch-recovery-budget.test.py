#!/usr/bin/env python3
"""Real shell launcher + real incident gate; only node/tmux are local fakes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
ROOT = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="codex-budget-") as td:
    root = Path(td)
    (root / "scripts/lib").mkdir(parents=True)
    (root / "bin").mkdir()
    for name in ["scripts/codex-channels.sh", "scripts/self-healing-attempt-gate.py", "scripts/lib/self-healing-launch.sh"]:
        shutil.copy2(ROOT / name, root / name)
    (root / "bin/node").write_text("#!/bin/sh\n[ \"${FIXTURE_AUTH_FAIL:-0}\" != 1 ]\n")
    (root / "bin/tmux").write_text("#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\nwith Path(os.environ['FIXTURE_CALLS']).open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')\nsys.exit(1 if sys.argv[1]=='new-session' else 0)\n")
    for f in (root / "bin").iterdir(): f.chmod(0o700)
    calls = root / "calls.jsonl"
    env = dict(os.environ, PATH=str(root / "bin")+os.pathsep+os.environ.get("PATH", ""), MAIN_AGENT_ID="fixture", FIXTURE_CALLS=str(calls), MARVEEN_SELF_HEALING_STATE_FILE=str(root / "state.json"), HOME=str(root / "home"))
    # Do not inherit a production service-manager claim into a fixture.
    env.pop("MARVEEN_SELF_HEALING_ATTEMPT_ID", None)
    env.pop("MARVEEN_SELF_HEALING_GATE_MANAGED", None)
    def gate(*args, environment=None):
        return subprocess.run(["python3", str(root / "scripts/self-healing-attempt-gate.py"), *args], env=environment or env, text=True, capture_output=True, timeout=10)
    def launch(environment=None, *args):
        return subprocess.run(["bash", str(root / "scripts/codex-channels.sh"), *args], env=environment or env, text=True, capture_output=True, timeout=10)
    for i in range(2):
        result = launch()
        assert result.returncode == 1, result.stderr
    before = calls.read_text()
    denied = launch()
    assert denied.returncode == 73 and calls.read_text() == before
    state = json.loads(gate("status", "main-channels").stdout)
    assert state["failures"] == 2 and state["blocked"] is True
    rows = [json.loads(line) for line in before.splitlines()]
    assert [r for r in rows if r[0] == "kill-session"] == [["kill-session", "-t", "=fixture-channels:"]] * 2
    assert len([r for r in rows if r[0] == "new-session"]) == 2
    print("PASS: two real launcher failures block a third before any tmux mutation")
    print("PASS: Codex launcher targets only its exact session")
    # Failed auth consumes one attempt, without killing the existing pane.
    auth_env = dict(env, FIXTURE_AUTH_FAIL="1", MARVEEN_SELF_HEALING_STATE_FILE=str(root / "auth.json"))
    assert launch(auth_env).returncode == 1 and calls.read_text() == before
    state = json.loads(gate("status", "main-channels", environment=auth_env).stdout)
    assert state["failures"] == 1 and state["active"] is None
    print("PASS: failed preflight preserves the old pane and records one failure")
    # A claimed parent owns the result; its child must not claim or charge twice.
    parent_env = dict(env, MARVEEN_SELF_HEALING_STATE_FILE=str(root / "parent.json"))
    parent = json.loads(gate("claim", "main-channels", "channel-monitor", environment=parent_env).stdout)
    child_env = dict(parent_env, MARVEEN_SELF_HEALING_ATTEMPT_ID=parent["attempt_id"])
    assert launch(child_env).returncode == 1
    state = json.loads(gate("status", "main-channels", environment=parent_env).stdout)
    assert state["active"]["id"] == parent["attempt_id"] and state["failures"] == 0
    assert gate("fail", "main-channels", parent["attempt_id"], "parent observed failed child", environment=parent_env).returncode == 0
    before = calls.read_text()
    assert launch(dict(child_env, MARVEEN_SELF_HEALING_ATTEMPT_ID="wrong-token")).returncode == 73
    assert calls.read_text() == before
    print("PASS: inherited ownership is verified and never double-counted")
    # Pane mode is controlled by the caller's explicit manual/automatic API path.
    assert launch(env, "--pane").returncode == 0
    state = json.loads(gate("status", "main-channels").stdout)
    assert state["blocked"] is True and state["failures"] == 2
    print("PASS: pane mode does not silently reset the automatic incident budget")
