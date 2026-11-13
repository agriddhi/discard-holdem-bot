"""For 'I called their bet/raise' showdown hands: what fraction did we win,
and what was the pot-odds break-even we needed?  Calibrates the discount.

Usage: py -3.11 call_calibration.py <match.log> [bot_label]
"""
import re
import sys

me = sys.argv[2] if len(sys.argv) > 2 else "A"
opp = "B" if me == "A" else "A"

net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")
act_re = re.compile(r"\b([AB])([fxcr])(\d*)")

n = wins = ties = 0
tot_net = 0
big_losses = []

for line in open(sys.argv[1], encoding="utf-8"):
    if "showdown" not in line:
        continue
    nm = net_re.search(line.rstrip())
    if not nm:
        continue
    net = int(nm.group(2)) if nm.group(1) == me else int(nm.group(4))
    body = line.split("|")
    acts = " ".join(body[3:-1]) if len(body) >= 5 else ""

    # did I call a bet/raise at some point?
    called_facing = False
    my_last = None
    opp_aggr = False
    for seat, a, amt in act_re.findall(acts):
        if seat == opp:
            if a == "r":
                opp_aggr = True
            elif a in ("f", "x"):
                opp_aggr = False
        else:
            if a == "c" and opp_aggr:
                called_facing = True
            if a in ("r", "c", "x"):
                opp_aggr = False if a == "r" else opp_aggr
                if a == "r":
                    pass
            if a == "f":
                pass
    if not called_facing:
        continue
    n += 1
    tot_net += net
    if net > 0:
        wins += 1
    elif net == 0:
        ties += 1
    if net <= -60:
        big_losses.append(line.strip()[:150])

if n:
    print(f"{sys.argv[1]} (us={me})")
    print(f"  called-then-showdown: {n} hands, wins {wins} ({100 * wins / n:.1f}%), "
          f"ties {ties}, net {tot_net:+d} ({tot_net / n:+.2f}/hand)")
    print(f"  biggest losses:")
    for l in big_losses[:4]:
        print(f"    {l}")
