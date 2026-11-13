"""Dump every preflop fold to their raise where our offline p >= 0.66,
tagged with the spot type (squeeze = we limped first, bb = they opened
into us, rr = we raised first) so we can check the decision in context.

Usage: py -3.11 highp_folds.py [glob ...]
"""
import re
import sys
import glob

sys.path.insert(0, ".")
from bot import Bot  # noqa: E402

hole_re = re.compile(r"\b([AB]): ((?:[2-9TJQKA][shdc] ?){3})\s+([AB]):")
bhole_re = re.compile(r"\b([AB]): ((?:[2-9TJQKA][shdc] ?){3})\s*\|")
act_re = re.compile(r"\b([AB])([fxcr])(\d*)")
label_re = re.compile(r"^\s*([AB])\s+(.+?)\s+net\s+")
btn_re = re.compile(r"button ([AB])")


def is_us(label):
    return label.replace("\\", "/").split("/")[-1] == "bot.py"


pats = sys.argv[1:] or ["logs_st*/match.log", "logs_rd*/match.log"]
files = sorted({f for p in pats for f in glob.glob(p) if "smoke" not in f})
bot = Bot()

n_dump = 0
for path in files:
    lines = open(path, encoding="utf-8").read().splitlines()
    our_seat = None
    for line in lines:
        m = label_re.match(line)
        if m and is_us(m.group(2)):
            our_seat = m.group(1)
    if our_seat is None:
        continue
    for line in lines:
        if "|" not in line or "preflop:" not in line:
            continue
        hm = hole_re.search(line)
        bm = bhole_re.search(line)
        btn = btn_re.search(line)
        if not hm or not bm or not btn:
            continue
        holes = {hm.group(1): hm.group(2).split(),
                 bm.group(1): bm.group(2).split()}
        p = float(bot.equity3(holes[our_seat], [], 600).max())
        if p < 0.66:
            continue
        body = line.split("|")
        acts = " ".join(body[3:-1])
        seg = acts.split("preflop:")[1]
        for st in ("flop:", "turn:", "river:"):
            seg = seg.split(st)[0]
        # walk actions until our fold
        my_actions = 0
        their_raise = 0
        our_raise = 0
        dumped = False
        for seat, a, amt in act_re.findall(seg):
            if dumped:
                break
            if seat == our_seat:
                my_actions += 1
                if a == "r":
                    our_raise += 1
                elif a == "f":
                    if their_raise > our_raise:
                        kind = ("rr" if our_raise > 0
                                else "bb-open" if my_actions == 1
                                else "squeeze")
                        print("%-14s p=%.3f us=%s btn=%s [%s] %s"
                              % (path.split(chr(92))[0], p, our_seat,
                                 btn.group(1), kind, seg.strip()[:90]))
                        n_dump += 1
                        dumped = True
            else:
                if a == "r":
                    their_raise += 1
print(f"\n{n_dump} high-p folds dumped")
