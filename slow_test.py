"""Slow-machine stress test: can the bot still finish inside the bank?

The grader's box may be slower than this one (or have 1 vCPU while we
have many).  Our Stage-2 match has used 42-65 s of a 150 s bank here,
so a 2-3x slower machine could breach it, and an exhausted time bank
FORFEITS the whole match.

This builds a slowed copy of the bot (an artificial delay inside every
equity call, emulating a slower CPU) and checks that:
  * the match still completes (no forfeit)
  * the bot's own time used stays inside the bank
  * the watchdog in n_for() actually shrinks the sample count and saves us

Usage: py -3.11 slow_test.py [factor]
"""
import os
import re
import shutil
import subprocess
import sys

FACTOR = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0

src = open("dist/bot.py", encoding="utf-8").read()

# Insert an artificial per-call delay inside equity3/equity2 to emulate a
# slower CPU.  The delay is scaled by the sample count, like real compute.
# Emulate a slower CPU: the extra time is spent INSIDE the timed region,
# exactly like a slower machine would spend it.  (A delay outside the
# timing would be invisible to the bot's own cost accounting and would
# not test what we want to test.)
slow = src.replace(
    "    def equity3(self, hole, board, n):",
    "    def _slow(self, n):\n"
    "        import time as _t\n"
    f"        _t.sleep({FACTOR} * 0.00035 * n)\n\n"
    "    def equity3(self, hole, board, n):")
slow = slow.replace(
    "        t0 = time.perf_counter()\n        eqs, _ = EQ.equity_mc",
    "        t0 = time.perf_counter()\n        self._slow(n)\n"
    "        eqs, _ = EQ.equity_mc")
slow = slow.replace(
    "        t0 = time.perf_counter()\n        eq = EQ.equity_mc",
    "        t0 = time.perf_counter()\n        self._slow(n)\n"
    "        eq = EQ.equity_mc")

os.makedirs("logs_slowtest", exist_ok=True)
out = "dist/bot_slow.py"
open(out, "w", encoding="utf-8", newline="\n").write(slow)
print(f"built slowed bot (x{FACTOR}) -> {out}")

env = dict(os.environ)
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    env[v] = "1"

print("\n--- Stage 2 shape (1000 hands, 75 s bank per leg) ---")
r = subprocess.run(["py", "-3.11", "engine.py", out,
                    "example_bots\\value_bot.py", "--stage", "2",
                    "--seed", "111", "--log-dir", "logs_slowtest"],
                   capture_output=True, text=True, env=env, timeout=1800)
for line in r.stdout.splitlines():
    if "net" in line or "Result" in line or "Capped" in line:
        print("   ", line.strip())
forfeit = "forfeit" in r.stdout
print(f"    FORFEIT: {forfeit}")
if forfeit:
    print("    !! the slowed bot exhausted its bank -- see the watchdog note")
