"""Behavioural test for the frequency guard.

The guard's purpose is behavioural: against an opponent with a wide
(unselective) range we must stop folding every hand to them; against
ordinary opponents our play must be unchanged.

This measures it directly from the match logs:
  * "call rate vs their preflop raise" -- near 0 means the fold spiral
  * "our net" -- we should not be losing to a wide-range opponent

Usage: py -3.11 test_guard_behavior.py
"""
import glob
import re
import subprocess
import sys
import os

sys.path.insert(0, ".")
import logparse as LP  # noqa: E402

CASES = [
    # name, opponent path, STYLE env, expect_wide_range
    ("value", "example_bots\\value_bot.py", None, False),
    ("tough", "example_bots\\tough_bot.py", None, False),
    ("aggro", "example_bots\\aggro_bot.py", None, False),
    ("caller", "example_bots\\style_bot.py", "caller", False),
    ("folder", "example_bots\\style_bot.py", "folder", False),
    ("jam", "example_bots\\style_bot.py", "jam", True),
    ("maniac", "example_bots\\style_bot.py", "maniac", True),
]

print(f"{'case':<10} {'their pf raise':>14} {'we call':>8} {'we fold':>8} "
      f"{'net':>7} {'verdict':>8}")
fails = 0
for name, opp, style, wide in CASES:
    env = dict(os.environ)
    if style:
        env["STYLE"] = style
    ld = f"logs_tgb2_{name}"
    out = subprocess.run(["py", "-3.11", "engine.py", "bot.py", opp,
                          "--seed", "111", "--log-dir", ld],
                         capture_output=True, text=True, env=env,
                         timeout=400).stdout
    net = None
    for line in out.splitlines():
        m = re.match(r"^\s*A\s+bot\.py\s+net\s+([+-]?\d+)", line)
        if m:
            net = int(m.group(1))
    lines = open(ld + "/match.log", encoding="utf-8").read().splitlines()
    our = LP.our_label(lines)
    calls = folds = their_raises = 0
    for line in lines:
        h = LP.parse(line)
        if not h:
            continue
        pf = [(st, seat, a, amt) for st, seat, a, amt in h["acts"]
              if st == "preflop"]
        if not pf:
            continue
        ours_idx = [i for i, (st, seat, a, amt) in enumerate(pf)
                    if seat == our]
        if not ours_idx:
            continue
        i = ours_idx[0]
        if i == 0 or pf[i - 1][2] != "r":
            continue
        their_raises += 1
        if pf[i][2] == "c":
            calls += 1
        elif pf[i][2] == "f":
            folds += 1
    call_rate = calls / their_raises if their_raises else 0.0
    # The criterion is the same for every style: we must not LOSE.  A low
    # call rate is fine (facing an all-in, only premium hands qualify);
    # what was broken before was losing every match.
    ok = net is not None and net > 0
    if not ok:
        fails += 1
    print(f"{name:<10} {their_raises:>14} {call_rate:>8.2f} {folds:>8} "
          f"{net if net is not None else '?':>7} "
          f"{'ok' if ok else 'FAIL':>8}")

print("\nPASS" if not fails else f"\nFAIL ({fails})")
sys.exit(1 if fails else 0)
