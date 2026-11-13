"""Run the 14-seed ladder and report raw + capped totals.

Usage: py -3.11 ladder.py [bot.py] [prefix] [seeds...]
"""
import glob
import re
import subprocess
import sys

BOT = sys.argv[1] if len(sys.argv) > 1 else "bot.py"
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "logs_ladder"
SEEDS = [int(a) for a in sys.argv[3:] if a.isdigit()] or \
    [111, 222, 5, 7, 8, 9, 10, 11, 12, 13, 14, 17, 605522686]

net_re = re.compile(r"^\s*([AB])\s+(\S+)\s+net\s+([+-]?\d+)")
CAP = 400


def match(seed, bot_first=True):
    ld = f"{PREFIX}_{seed}"
    if bot_first:
        cmd = ["py", "-3.11", "engine.py", BOT, "example_bots\\value_bot.py",
               "--seed", str(seed), "--log-dir", ld]
    else:
        cmd = ["py", "-3.11", "engine.py", "example_bots\\value_bot.py", BOT,
               "--seed", str(seed), "--log-dir", ld]
    out = subprocess.run(cmd, capture_output=True, text=True,
                         timeout=400).stdout
    raw = None
    seat = None
    for line in out.splitlines():
        m = net_re.match(line)
        if m and m.group(2).replace("\\", "/").split("/")[-1] == \
                BOT.replace("\\", "/").split("/")[-1]:
            seat = m.group(1)
            raw = int(m.group(3))
    if raw is None:
        return None, None, None
    forfeit = "wins by forfeit" in out
    if forfeit:
        cap = CAP if "A wins by forfeit" in out else -CAP
    else:
        cap = max(-CAP, min(CAP, raw))
    return raw, cap, seat


print(f"bot={BOT}")
print(f"{'seed':>10} {'seat':>4} {'raw':>7} {'capped':>7}")
raw_t = cap_t = 0
for seed in SEEDS:
    bot_first = seed != 333
    raw, cap, seat = match(seed, bot_first)
    if raw is None:
        print(f"{seed:>10}  ERROR")
        continue
    raw_t += raw
    cap_t += cap
    print(f"{seed:>10} {seat or '?':>4} {raw:>7} {cap:>7}")
print(f"{'TOTAL':>10} {'':>4} {raw_t:>7} {cap_t:>7}")
