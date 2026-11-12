"""Safety contract for scripts/dev.sh stop; no real processes or ports are used.

Run with: python -m unittest discover -s zg-tsp-docs/scripts -p test_dev_stop.py
The PID identity is the hexadecimal encoding of ps output with trailing newlines
removed, as in shell command substitution.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scripts" / "dev.sh"
PS_OUTPUT = "Mon Jan  2 03:04:05 2023 /usr/bin/python -m uvicorn app.main:app\n"
IDENTITY = PS_OUTPUT.rstrip("\n").encode().hex()

# Source the actual script in the same shell so its kill builtin is shadowed.
# $0 must be dev.sh because the script uses it to determine its repository root.
WRAPPER = r'''
kill() {
  printf '%s\n' "kill $*" >> "$CALLS"
  if [ "${1:-}" = "-0" ]; then [ "${STALE:-0}" != 1 ]; return; fi
  [ "${FAIL_KILL:-0}" != 1 ]
}
pkill() { printf '%s\n' "pkill $*" >> "$CALLS"; return 0; }
ps() {
  printf '%s\n' "ps $*" >> "$CALLS"
  [ "${STALE:-0}" != 1 ] || return 1
  printf '%s\n' "$PS_LINE"
}
lsof() {
  printf '%s\n' "lsof $*" >> "$CALLS"
  [ -n "${PORT_PID:-}" ] || return 1
  printf '%s\n' "$PORT_PID"
}
sleep() { printf '%s\n' "sleep $*" >> "$CALLS"; }
set -- stop
. "$0"
'''


class StopSafetyTests(unittest.TestCase):
    def run_stop(self, record=None, *, stale=False, port_pid="", fail_kill=False):
        # Keep temporary artifacts under docs, isolated from the real .dev-logs.
        with tempfile.TemporaryDirectory(dir=ROOT / "zg-tsp-docs") as tmp:
            log_dir = Path(tmp) / "logs"
            log_dir.mkdir()
            pid_file = log_dir / "dev.pids"
            if record is not None:
                pid_file.write_text(record, encoding="utf-8")
            calls = Path(tmp) / "calls"
            calls.touch()
            env = os.environ.copy()
            env.update(
                REPOS_DIR=str(ROOT), LOG_DIR=str(log_dir), CALLS=str(calls),
                PS_LINE=PS_OUTPUT.rstrip("\n"), STALE="1" if stale else "0",
                PORT_PID=port_pid, FAIL_KILL="1" if fail_kill else "0",
                SERVER_PORT="48123", WEB_PORT="48124",
            )
            result = subprocess.run(
                ["/bin/sh", "-c", WRAPPER, str(DEV)], env=env,
                text=True, capture_output=True, timeout=10,
            )
            return result, calls.read_text().splitlines(), (
                pid_file.read_text() if pid_file.exists() else None
            )

    def assert_no_signals(self, calls):
        signals = [c for c in calls if c.startswith("pkill ") or
                   (c.startswith("kill ") and not c.startswith("kill -0 "))]
        self.assertEqual(signals, [], calls)

    def test_verified_identity_signals_only_recorded_pid(self):
        result, calls, _ = self.run_stop(f"server 12345 {IDENTITY}\n", port_pid="99999")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c in ("kill 12345", "kill -TERM 12345") for c in calls), calls)
        self.assertFalse(any(c.startswith("pkill ") for c in calls), calls)
        self.assertFalse(any("99999" in c and c.startswith(("kill ", "pkill ")) for c in calls), calls)
        self.assertTrue(any(c.startswith("ps ") and "12345" in c for c in calls), calls)

    def test_stale_pid_is_not_signalled(self):
        record = f"server 12345 {IDENTITY}\n"
        result, calls, remaining = self.run_stop(record, stale=True)
        self.assert_no_signals(calls)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(remaining, record)

    def test_malformed_and_legacy_records_are_not_signalled(self):
        for record in (
            "server 12345\n", "server not-a-pid deadbeef\n", "server 0 deadbeef\n",
            "server -1 deadbeef\n", "server 12345 not-hex\n",
            f"server 12345 {IDENTITY} extra\n", f"unknown 12345 {IDENTITY}\n",
        ):
            with self.subTest(record=record):
                _, calls, _ = self.run_stop(record)
                self.assert_no_signals(calls)

    def test_legacy_records_are_preserved_and_reported(self):
        record = "server 12345\n  web\t23456  \nserver 34567 not-hex"
        result, calls, remaining = self.run_stop(record)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(remaining, record + "\n")
        self.assertIn("手动核查", result.stdout + result.stderr)
        self.assert_no_signals(calls)
        self.assertFalse(any(c.startswith("ps ") for c in calls), calls)

    def test_legacy_record_does_not_block_verified_record(self):
        result, calls, remaining = self.run_stop(
            f"server 12345\nweb 23456 {IDENTITY}\n"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(remaining, "server 12345\n")
        self.assertTrue(any(c in ("kill 23456", "kill -TERM 23456") for c in calls), calls)
        self.assertFalse(any("12345" in c and c.startswith(("kill ", "ps ")) for c in calls), calls)

    def test_occupied_ports_without_pid_file_are_not_signalled(self):
        _, calls, _ = self.run_stop(port_pid="99999")
        self.assert_no_signals(calls)

    def test_identity_mismatch_is_not_signalled(self):
        _, calls, _ = self.run_stop(f"server 12345 {'different process'.encode().hex()}\n")
        self.assert_no_signals(calls)

    def test_kill_failure_is_not_reported_as_success(self):
        result, calls, remaining = self.run_stop(
            f"server 12345 {IDENTITY}\n", fail_kill=True
        )
        self.assertTrue(any(c in ("kill 12345", "kill -TERM 12345") for c in calls), calls)
        self.assertNotIn("已停止 server", result.stdout)
        self.assertTrue(result.returncode != 0 or (remaining and "12345" in remaining),
                        "failure must be surfaced or the record retained for retry")


if __name__ == "__main__":
    unittest.main()
