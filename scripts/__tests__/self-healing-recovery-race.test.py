#!/usr/bin/env python3
"""Exercise independent recovery actors against one disposable incident gate."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]

with tempfile.TemporaryDirectory(prefix="marveen-recovery-race-", dir="/tmp") as td:
    root = Path(td) / "install"
    (root / "scripts").mkdir(parents=True)
    (root / "store").mkdir()
    (root / "scripts/lib").mkdir()
    shutil.copy2(ROOT / "scripts/lib/self-healing-launch.sh", root / "scripts/lib/self-healing-launch.sh")
    shutil.copy2(ROOT / "scripts/main-extra-plugins-settings.sh", root / "scripts/main-extra-plugins-settings.sh")
    shutil.copy2(ROOT / "scripts/channel-watchdog.sh", root / "scripts/channel-watchdog.sh")
    shutil.copy2(ROOT / "scripts/self-healing-attempt-gate.py", root / "scripts/self-healing-attempt-gate.py")
    (root / ".env").write_text("MAIN_AGENT_ID=drill\nMARVEEN_AGENT_BACKEND=codex\n", encoding="utf-8")
    fakebin = root / "bin"
    fakebin.mkdir()
    calls = root / "tmux-calls.log"
    (fakebin / "tmux").write_text(
        "#!/bin/sh\n"
        "echo \"$1 $*\" >> \"$DRILL_TMUX_LOG\"\n"
        "case \"$1\" in has-session) exit 0;; respawn-pane) exit 0;; *) exit 0;; esac\n",
        encoding="utf-8",
    )
    (fakebin / "node").write_text("#!/bin/sh\ncase \"$1\" in *sync-owner-rules.mjs) exit 0;; *) exit 1;; esac\n", encoding="utf-8")
    # Deliberately no Claude binary: a Codex watchdog must not depend on it.
    for tool in ["python3", "bash", "grep", "head", "cut", "date", "cat", "mkdir", "sed", "tr", "awk", "flock", "sleep", "dirname", "uname", "id", "tail", "seq", "rm", "stat", "nohup", "touch", "basename"]:
        executable = sys.executable if tool == "python3" else shutil.which(tool)
        if executable:
            (fakebin / tool).symlink_to(executable)
    for path in fakebin.iterdir():
        if not path.is_symlink(): path.chmod(0o700)
    keepalive = root / "store/.channel-keepalive"
    keepalive.touch()
    old = time.time() - 3600
    os.utime(keepalive, (old, old))

    env = os.environ.copy()
    env.update({
        "PATH": str(fakebin),
        "DRILL_TMUX_LOG": str(calls),
        "MARVEEN_SELF_HEALING_STATE_FILE": str(root / "store/.self-healing-attempts.json"),
        "MARVEEN_SELF_HEALING_WATCH_SECONDS": "1",
        "MARVEEN_SELF_HEALING_POLL_SECONDS": "0.05",
        "MARVEEN_SELF_HEALING_STABLE_SECONDS": "0",
        "MARVEEN_SELF_HEALING_ACTIVE_SECONDS": "2",
    })

    assert shutil.which("claude", path=env["PATH"]) is None
    watchdog = subprocess.run(["bash", str(root / "scripts/channel-watchdog.sh")], env=env,
                              text=True, capture_output=True, timeout=15)
    assert watchdog.returncode == 0, watchdog.stderr
    assert any(line.startswith("respawn-pane ") for line in calls.read_text().splitlines()), watchdog.stdout
    assert "codex-channels.sh" in calls.read_text()
    time.sleep(1.4)  # isolated health watcher records the unverified restart as failure

    gate = root / "scripts/self-healing-attempt-gate.py"
    second = subprocess.run(["python3", str(gate), "claim", "main-channels", "systemd-supervisor"],
                            env=env, text=True, capture_output=True, timeout=10)
    assert second.returncode == 0, second.stderr
    second_id = json.loads(second.stdout)["attempt_id"]
    subprocess.run(["python3", str(gate), "fail", "main-channels", second_id,
                    "isolated systemd startup health did not pass"], env=env, check=True,
                   text=True, capture_output=True, timeout=10)

    third = subprocess.run(["python3", str(gate), "claim", "main-channels", "channel-monitor"],
                           env=env, text=True, capture_output=True, timeout=10)
    state = json.loads(subprocess.run(["python3", str(gate), "status", "main-channels"], env=env,
                                      check=True, text=True, capture_output=True, timeout=10).stdout)
    actual_respawns = sum(line.startswith("respawn-pane ") for line in calls.read_text().splitlines())
    assert third.returncode == 3, (third.returncode, third.stdout, third.stderr)
    assert state["failures"] == 2 and state["blocked"] is True, state
    assert actual_respawns == 1, actual_respawns
    print("PASS: channel-watchdog and systemd-supervisor share one persistent incident budget")
    print("PASS: after two cross-actor failures, channel-monitor third claim is STOPped")
    print("PASS: only one mocked Codex respawn was invoked, with no Claude binary or service manager")
