"""Measure avg hand category at showdown (from match.log text) to calibrate
the aggression discount baseline.
"""
import re
import sys
import glob
from collections import Counter

cat_name = {
    "high card": 0, "one pair": 1, "two pair": 2, "three of a kind": 3,
    "straight": 4, "flush": 5, "full house": 6, "four of a kind": 7,
    "straight flush": 8,
}
pat = re.compile(r"showdown \((?:\w+ )?([a-z ]+?), (?:\w+ )?([a-z ]+?)\)")

counts = Counter()
files = sys.argv[1:] or glob.glob("logs_v*/match.log") + glob.glob("logs_s1_*/match.log")
for f in files:
    for line in open(f, encoding="utf-8"):
        m = pat.search(line)
        if m:
            for g in m.groups():
                counts[cat_name.get(g.strip(), -1)] += 1

total = sum(counts.values())
if total:
    print(f"showdown hands analyzed: {total}")
    avg = 0.0
    for k in sorted(counts):
        pct = 100 * counts[k] / total
        avg += k * counts[k] / total
        print(f"  cat {k}: {counts[k]:>6} ({pct:4.1f}%)")
    print(f"baseline avg category = {avg:.3f}")
