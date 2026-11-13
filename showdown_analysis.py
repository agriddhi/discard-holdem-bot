"""Classify showdown hands by betting pattern -> find the leak.

Usage: py -3.11 showdown_analysis.py <match.log> [bot_label]
"""
import re
import sys
from collections import defaultdict

path = sys.argv[1]
me = sys.argv[2] if len(sys.argv) > 2 else "A"

hand_re = re.compile(r"^(L\d+) #(\d+)\s+button (\w)")
net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")

# action token: <seat><f|x|c|r><amount?>
act_re = re.compile(r"\b([AB])([fxcr])(\d*)")

stats = defaultdict(lambda: [0, 0])   # bucket -> [net, hands]

for line in open(path, encoding="utf-8"):
    if "showdown" not in line:
        continue
    nm = net_re.search(line.rstrip())
    if not nm:
        continue
    net = int(nm.group(2)) if nm.group(1) == me else int(nm.group(4))

    # action sequence part is between '|' board/discards section and '| showdown'
    body = line.split("|")
    # find segment with 'preflop:' .. before 'showdown'
    acts = " ".join(body[3:-1]) if len(body) >= 5 else ""
    tokens = act_re.findall(acts)
    opp = "B" if me == "A" else "A"

    # did I face aggression (opp r) and call?
    my_last = None
    opp_r = False
    faced_raise_called = False
    bet_called = False      # I bet, they called (I was the aggressor)
    raised_called = False   # I raised, they called
    i_aggr = False
    for seat, act, amt in tokens:
        if seat == opp:
            if act == "r":
                if i_aggr:
                    faced_raise_called = False  # they re-raised over me
                opp_r = True
                i_aggr = False
            elif act == "c" and i_aggr:
                if my_last == "r":
                    raised_called = True
                elif my_last == "b":
                    bet_called = True
                i_aggr = False
            elif act == "f":
                i_aggr = False
                opp_r = False
        else:  # me
            if act in ("r",):
                my_last = "r"
                if not opp_r:
                    i_aggr = True
            elif act == "x":
                my_last = "x"
                if not opp_r:
                    i_aggr = False
                else:
                    i_aggr = False
            elif act == "c":
                if opp_r:
                    faced_raise_called = True
                my_last = "c"
                opp_r = False
                i_aggr = False

    if faced_raise_called:
        bucket = "I called their bet/raise"
    elif raised_called:
        bucket = "I raised, they called"
    elif opp_r:
        bucket = "they raised, I folded? (sd impossible)"
    else:
        bucket = "checked down / I bet called"
    stats[bucket][0] += net
    stats[bucket][1] += 1

print(f"{path} (us = {me})  showdown hands by pattern")
for k, (n, h) in sorted(stats.items(), key=lambda kv: -abs(kv[1][0])):
    print(f"  {k:<34} {h:>4} hands  {n:>+7}  ({n / h:>+5.2f}/hand)")
