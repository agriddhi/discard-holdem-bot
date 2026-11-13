"""Both seats' net by POSITION (who is the button) from match.log.

Tells us whether the button advantage in our data is ours, theirs, or
inherent -- decides whether a position-aware adjustment is worth it.

Usage: py -3.11 pos2.py [logs_t*/match.log ...]
"""
import re
import sys
import glob

net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")
btn_re = re.compile(r"button (\w)")

pats = sys.argv[1:] or ["logs_t*/match.log"]
files = sorted({f for p in pats for f in glob.glob(p)})

# seat -> button? -> [net, hands]
b = {("A", True): [0, 0], ("A", False): [0, 0],
     ("B", True): [0, 0], ("B", False): [0, 0]}

for path in files:
    for line in open(path, encoding="utf-8"):
        nm = net_re.search(line.rstrip())
        bm = btn_re.search(line)
        if not nm or not bm:
            continue
        btn = bm.group(1)
        nets = {nm.group(1): int(nm.group(2)), nm.group(3): int(nm.group(4))}
        for seat, net in nets.items():
            r = b[(seat, seat == btn)]
            r[0] += net
            r[1] += 1

print(f"files: {len(files)}")
print(f"{'seat':<6} {'as BUTTON':>16} {'as BIG BLIND':>16} {'split':>8}")
for seat in ("A", "B"):
    (n0, h0), (n1, h1) = b[(seat, True)], b[(seat, False)]
    a0 = n0 / h0 if h0 else 0
    a1 = n1 / h1 if h1 else 0
    print(f"{seat:<6} {n0:>+7} ({h0}, {a0:>+.2f}) {n1:>+7} ({h1}, {a1:>+.2f}) "
          f"{a0 - a1:>+8.2f}")
