"""For each showdown, find who was the flop/turn/river aggressor and what
category they showed -> calibrate the equity discount for facing bets.
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
act_re = re.compile(r"\b([AB])([fxcr])(\d*)")

files = sys.argv[1:] or glob.glob("logs_v*/match.log") + glob.glob("logs_s1_*/match.log")
aggr_cat = Counter()      # category of player who bet/raised postflop
aggro_n = 0
shown = Counter()
for f in files:
    for line in open(f, encoding="utf-8"):
        m = pat.search(line)
        if not m:
            continue
        body = line.split("|")
        acts = " ".join(body[3:-1]) if len(body) >= 5 else ""
        # find postflop (after 'flop:') first aggressor: first r-token after flop:
        parts = re.split(r"\b(preflop|flop|turn|river):", acts)
        aggr = None
        for i in range(1, len(parts), 2):
            street, seg = parts[i], parts[i + 1]
            if street == "preflop":
                continue
            for seat, a, amt in act_re.findall(seg):
                if a == "r":
                    aggr = seat
                    break
            if aggr:
                break
        if aggr is None:
            continue
        idx = 0 if aggr == "A" else 1
        cat = cat_name.get(m.group(idx + 1).strip(), -1)
        if cat >= 0:
            aggr_cat[cat] += 1
            aggro_n += 1
        shown[cat_name.get(m.group(0).split(",")[0].strip().lstrip("("), -1)]

total = sum(aggr_cat.values())
if total:
    avg = sum(k * v for k, v in aggr_cat.items()) / total
    print(f"postflop aggressor showdowns: {total}")
    for k in sorted(aggr_cat):
        print(f"  cat {k}: {aggr_cat[k]:>5} ({100 * aggr_cat[k] / total:4.1f}%)")
    print(f"aggressor avg category = {avg:.3f}   (baseline all showdowns = 1.944)")
    print(f"weak (cat 0) rate = {100 * aggr_cat[0] / total:.1f}%  (baseline 8.1%)")
