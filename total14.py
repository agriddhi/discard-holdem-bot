"""Sum our net across match.log files (per-hand nets are printed there).

Usage: py -3.11 total14.py <seat: A|B> <file|glob> [<file|glob> ...]
"""
import re
import sys
import glob

net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")

seat = sys.argv[1]
assert seat in ("A", "B"), "first arg must be seat A or B"
files = sorted({f for p in sys.argv[2:] for f in glob.glob(p)})
total = 0
hands = 0
for path in files:
    t = 0
    h = 0
    for line in open(path, encoding="utf-8"):
        m = net_re.search(line.rstrip())
        if not m:
            continue
        t += int(m.group(2)) if m.group(1) == seat else int(m.group(4))
        h += 1
    print(f"{path:<32} {h:>5} hands {t:>+8}")
    total += t
    hands += h
print(f"seat {seat}: {len(files)} files {hands} hands GRAND TOTAL {total:+}")
