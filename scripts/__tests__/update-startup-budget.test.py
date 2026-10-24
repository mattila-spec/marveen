#!/usr/bin/env python3
"""Execute actual updater health functions and scope wrapper with fake I/O."""
import os, pathlib, subprocess, tempfile
root = pathlib.Path(__file__).resolve().parents[2]
src = (root / 'update.sh').read_text()
functions = [src.split('health_ok() {', 1)[1].split('\n}', 1)[0],
             src.split('_health() {', 1)[1].split('\n_restart() {', 1)[0]]
with tempfile.TemporaryDirectory(prefix='updater-startup-budget-') as tmp:
    d = pathlib.Path(tmp)
    for index, body in enumerate(functions):
        fn = 'health() {' + body + ('\n}' if index == 0 else '')
        harness = """
count=0
curl() { count=$((count+1)); [ "$count" -ge "$READY_AT" ]; }
sleep() { :; }
PORT=3420
WEB_PORT=3420
""" + fn + '\nhealth; rc=$?; printf "%s %s\\n" "$rc" "$count"\n'
        for ready, expected in [(1, '0 1'), (41, '0 41'), (121, '1 120')]:
            result = subprocess.check_output(['bash', '-c', harness], env={**os.environ, 'READY_AT': str(ready)}, text=True).strip()
            assert result == expected, (index, ready, result, expected)
    line = next(x for x in src.splitlines() if "bash -c 'bash" in x)
    wrapper = line.split("bash -c '", 1)[1].split("' --", 1)[0]
    child = d / 'finalizer.sh'
    child.write_text('printf failed > "$1"\nexit 6\n')
    resultfile = d / 'result'
    outer = 'bash -c "$1" -- "$2" "$3" || printf duplicate > "$4"'
    subprocess.run(['bash', '-c', outer, '--', wrapper, str(child), str(resultfile), str(d/'fallback')], check=True)
    assert resultfile.read_text() == 'failed'
    assert not (d/'fallback').exists()
print('PASS: both health paths accept a 40-second startup, remain bounded, and failed finalizer is not launched twice')
