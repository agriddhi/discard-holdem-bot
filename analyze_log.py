"""Aggregate a match.log: where do our chips come from / go to?

Usage: py -3.11 analyze_log.py <match.log> [bot_label]
bot_label: which seat is "us" (default 'A').
"""
import re
import sys
from collections import defaultdict

path = sys.argv[1]
me = sys.argv[2] if len(sys.argv) > 2 else "A"

agg = defaultdict(lambda: [0, 0])   # bucket -> [net, hands]
ends = defaultdict(lambda: [0, 0])
street_lost = defaultdict(lambda: [0, 0])

hand_re = re.compile(r"^(L\d+) #(\d+)\s+button (\w)")
net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")

for line in open(path, encoding="utf-8"):
    m = hand_re.match(line)
    if not m:
        continue
    nm = net_re.search(line.rstrip())
    if not nm:
        continue
    net = int(nm.group(2)) if nm.group(1) == me else int(nm.group(4))

    # classify ending.  NOTE: the log prints "fold <seat0> <net0>, <seat1>
    # <net1>" -- the name after "fold" is seat 0 (the button), NOT the
    # folder.  On a fold hand exactly one net is negative: the folder.
    if "showdown" in line:
        kind = "showdown"
    elif re.search(r"\| fold ", line):
        kind = "opp folds" if net > 0 else "I fold"
    else:
        kind = "other"

    # who had the last aggression? crude: preflop..river segments
    seg = line.split("|")
    last_street = "?"
    for s in seg[3:8]:
        if ":" in s:
            last_street = s.split(":")[0].strip()

    agg[kind][0] += net
    agg[kind][1] += 1
    ends[kind][0] += net
    ends[kind][1] += 1

print(f"{path}  (us = seat {me})")
print(f"{'ending':<14} {'hands':>6} {'net':>8} {'avg':>7}")
for k, (n, h) in sorted(agg.items()):
    print(f"{k:<14} {h:>6} {n:>+8} {n / h:>+7.2f}")
tot_n = sum(v[0] for v in agg.values())
tot_h = sum(v[1] for v in agg.values())
print(f"{'TOTAL':<14} {tot_h:>6} {tot_n:>+8} {tot_n / tot_h:>+7.2f}")
