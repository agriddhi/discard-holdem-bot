"""Do we lose more calling a RE-RAISE than calling an OPEN bet?

Both use the same range model today; if the win rates differ, we need a
separate threshold for "they raised over us".

Usage: py -3.11 call_vs_raise.py [logs_t*/match.log ...] [bot_label]
"""
import re
import sys
import glob

me = sys.argv[-1] if sys.argv[-1] in ("A", "B") else "A"
args = [a for a in sys.argv[1:] if a not in ("A", "B")]
files = sorted({f for a in (args or ["logs_t*/match.log", "logs_v*/match.log"])
                for f in glob.glob(a)})

net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")
act_re = re.compile(r"\b([AB])([fxcr])(\d*)")
opp = "B" if me == "A" else "A"

# buckets: how WE ended up calling their aggression on the last such street
stats = {"open bet": [0, 0, 0], "re-raise over us": [0, 0, 0]}
# [net, hands, wins]

for path in files:
    for line in open(path, encoding="utf-8"):
        if "showdown" not in line:
            continue
        nm = net_re.search(line.rstrip())
        if not nm:
            continue
        net = int(nm.group(2)) if nm.group(1) == me else int(nm.group(4))
        body = line.split("|")
        acts = " ".join(body[3:-1]) if len(body) >= 5 else ""

        # split into street segments
        parts = re.split(r"\b(preflop|flop|turn|river):", acts)
        segs = [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]

        # walk streets in order; remember the LAST street where we called
        # facing their aggression, and whether they had raised over us
        kind = None
        last_was_over = False
        for street, seg in segs:
            last = None          # 'me_r' if we raised last, else None
            i_aggr = False       # they put in a raise this street
            for seat, a, amt in act_re.findall(seg):
                if seat == opp:
                    if a == "r":
                        i_aggr = True
                        over = (last == "me_r")
                    elif a in ("f", "x"):
                        i_aggr = False
                else:  # me
                    if a == "r":
                        last = "me_r"
                        i_aggr = False
                    elif a == "c":
                        if i_aggr:
                            kind = "re-raise over us" if last_was_over \
                                else "open bet"
                        last = None
                        i_aggr = False
                    else:
                        last = None
                        i_aggr = False
                if seat == opp and a == "r":
                    last_was_over = (last == "me_r")
        if kind:
            stats[kind][0] += net
            stats[kind][1] += 1
            stats[kind][2] += 1 if net > 0 else 0

print(f"files: {len(files)}  (us = {me})")
print(f"{'when we called...':<20} {'hands':>6} {'win%':>6} {'net':>8} {'avg':>7}")
for k, (n, h, w) in stats.items():
    if h:
        print(f"{k:<20} {h:>6} {100 * w / h:>5.1f}% {n:>+8} {n / h:>+7.2f}")
