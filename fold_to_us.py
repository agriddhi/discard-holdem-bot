"""Their response to OUR aggression, by street: fold / call / raise / over.

From match.log action tokens: after one of our raises on a street, what
does the opponent do next on that street?  (Fold = we win the pot.)

Usage: py -3.11 fold_to_us.py [logs_t*/match.log ...]
"""
import re
import sys
import glob
from collections import defaultdict

act_re = re.compile(r"\b([AB])([fxcr])(\d*)")
net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")

me = sys.argv[-1] if sys.argv[-1] in ("A", "B") else "A"
args = [a for a in sys.argv[1:] if a not in ("A", "B")]
pats = args or ["logs_t*/match.log"]
files = sorted({f for p in pats for f in glob.glob(p)})
opp = "B" if me == "A" else "A"

# street -> response -> count
resp = defaultdict(lambda: defaultdict(int))
# street -> response -> [net, hands]
won = defaultdict(lambda: defaultdict(lambda: [0, 0]))

for path in files:
    for line in open(path, encoding="utf-8"):
        if "|" not in line:
            continue
        nm = net_re.search(line.rstrip())
        if not nm:
            continue
        net = int(nm.group(2)) if nm.group(1) == me else int(nm.group(4))
        body = line.split("|")
        acts = " ".join(body[3:-1]) if len(body) >= 5 else ""
        parts = re.split(r"\b(preflop|flop|turn|river):", acts)
        segs = [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]

        for street, seg in segs:
            awaiting = False      # we just raised on this street
            for seat, a, amt in act_re.findall(seg):
                if seat == me and a == "r":
                    if awaiting:   # they responded to previous raise already
                        pass
                    awaiting = True
                elif seat == opp and awaiting:
                    key = {"f": "fold", "c": "call",
                           "r": "raise-over", "x": "check"}.get(a, a)
                    resp[street][key] += 1
                    won[street][key][0] += net
                    won[street][key][1] += 1
                    awaiting = False
                elif seat == opp:
                    awaiting = False
                elif seat == me and a in ("c", "x", "f"):
                    awaiting = False

print(f"files: {len(files)}  (us = {me})")
print(f"{'street':<9} {'response':<11} {'n':>5} {'net':>8} {'avg':>8}")
for street in ("preflop", "flop", "turn", "river"):
    r = resp[street]
    tot = sum(r.values())
    if not tot:
        continue
    for key in ("fold", "call", "raise-over"):
        n = r.get(key, 0)
        if not n:
            continue
        w = won[street][key]
        print(f"{street:<9} {key:<11} {n:>5} {w[0]:>8} {w[0] / w[1]:>+8.2f}")
    print()
