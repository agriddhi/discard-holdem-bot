"""Their aggression -> OUR response, by street (mirror of fold_to_us).

Usage: py -3.11 their_aggr.py [glob ...] [A|B]
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

# street -> our response -> [net, hands]
resp = defaultdict(lambda: defaultdict(lambda: [0, 0]))
# street -> our response -> count (for rates)
cnt = defaultdict(lambda: defaultdict(int))

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
            awaiting = False      # they just raised; our response pending
            for seat, a, amt in act_re.findall(seg):
                if seat == opp and a == "r":
                    awaiting = True
                elif seat == me and awaiting:
                    key = {"f": "fold", "c": "call",
                           "r": "raise-over", "x": "check"}.get(a, a)
                    cnt[street][key] += 1
                    resp[street][key][0] += net
                    resp[street][key][1] += 1
                    awaiting = False
                elif seat == me:
                    awaiting = False
                elif seat == opp:
                    awaiting = False

print(f"files: {len(files)}  (us = {me})")
print(f"{'street':<9} {'response':<11} {'n':>5} {'net':>8} {'avg':>8}")
for street in ("preflop", "flop", "turn", "river"):
    c = cnt[street]
    if not sum(c.values()):
        continue
    for key in ("fold", "call", "raise-over"):
        n = c.get(key, 0)
        if not n:
            continue
        w = resp[street][key]
        print(f"{street:<9} {key:<11} {n:>5} {w[0]:>8} {w[0] / w[1]:>+8.2f}")
    print()
