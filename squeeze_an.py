"""Distribution of OUR hand strength (p = best-keep equity vs random) in
spots where they raised preflop and we had to respond.

Explains the "we fold 100% of their preflop raises" observation:
is it correct folding (our hands are weak there) or a defend leak?

Usage: py -3.11 squeeze_an.py [glob ...]
"""
import re
import sys
import glob

sys.path.insert(0, ".")
from bot import Bot  # noqa: E402

net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")
hole_re = re.compile(r"\b([AB]): ((?:[2-9TJQKA][shdc] ?){3})\s+([AB]):")
bhole_re = re.compile(r"\b([AB]): ((?:[2-9TJQKA][shdc] ?){3})\s*\|")
act_re = re.compile(r"\b([AB])([fxcr])(\d*)")
label_re = re.compile(r"^\s*([AB])\s+(.+?)\s+net\s+")


def is_us(label):
    return label.replace("\\", "/").split("/")[-1] == "bot.py"


pats = sys.argv[1:] or ["logs_rd*/match.log"]
files = sorted({f for p in pats for f in glob.glob(p) if "smoke" not in f})

bot = Bot()
rows = []          # (kind, facing_reraise, p, net_for_us)

for path in files:
    txt = open(path, encoding="utf-8").read().splitlines()
    our_seat = None
    for line in txt:
        m = label_re.match(line)
        if m and is_us(m.group(2)):
            our_seat = m.group(1)
    if our_seat is None:
        print("  !! no seat for " + path)
        continue
    for line in txt:
        if "|" not in line:
            continue
        nm = net_re.search(line.rstrip())
        hm = hole_re.search(line)
        bm = bhole_re.search(line)
        if not nm or not hm or not bm:
            continue
        holes = {hm.group(1): hm.group(2).split(),
                 bm.group(1): bm.group(2).split()}
        net = int(nm.group(2)) if nm.group(1) == our_seat else int(nm.group(4))
        body = line.split("|")
        acts = " ".join(body[3:-1]) if len(body) >= 5 else ""
        parts = re.split(r"\b(preflop|flop|turn|river):", acts)
        segs = [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]
        for street, seg in segs:
            if street != "preflop":
                continue
            my_raise = False
            opp_raise = False
            for seat, a, amt in act_re.findall(seg):
                if seat == our_seat:
                    if a == "r":
                        my_raise = True
                    elif a in ("f", "c"):
                        if opp_raise:
                            p = float(bot.equity3(holes[our_seat], [], 600).max())
                            key = "fold" if a == "f" else "call"
                            rows.append((key, my_raise, p, net))
                        opp_raise = False
                        my_raise = False
                else:  # opponent
                    if a == "r":
                        opp_raise = True
                    elif a in ("f", "c", "x"):
                        opp_raise = False

buckets = [(0.0, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.65),
           (0.65, 0.68), (0.68, 0.72), (0.72, 1.01)]
print("OUR response to their preflop raise  (files=%d)" % len(files))
hdr = "%-16s %6s %6s" % ("p bucket", "fold", "call")
print(hdr + "   squeezes (no raise of ours in front)")
for lo, hi in buckets:
    f = sum(1 for k, rr, p, _ in rows if not rr and k == "fold" and lo <= p < hi)
    c = sum(1 for k, rr, p, _ in rows if not rr and k == "call" and lo <= p < hi)
    print("[%4.2f,%4.2f)     %6d %6d" % (lo, min(hi, 1.0), f, c))

print("")
print("facing a reraise (we raised first):")
for lo, hi in buckets:
    f = sum(1 for k, rr, p, _ in rows if rr and k == "fold" and lo <= p < hi)
    c = sum(1 for k, rr, p, _ in rows if rr and k == "call" and lo <= p < hi)
    if f or c:
        print("[%4.2f,%4.2f)     %6d %6d" % (lo, min(hi, 1.0), f, c))

sq = [(k, p, n) for k, rr, p, n in rows if not rr]
rf = [(k, p, n) for k, rr, p, n in rows if rr]
fold_p = [p for k, p, _ in sq if k == "fold"]
call_p = [p for k, p, _ in sq if k == "call"]
print("")
print("squeeze spots: n=%d folds=%d calls=%d"
      % (len(sq), len(fold_p), len(call_p)))
if fold_p:
    print("  fold max_p=%.3f  folds with p>=0.66: %d"
          % (max(fold_p), sum(1 for p in fold_p if p >= 0.66)))
print("  call p values: %s" % [round(p, 3) for p in call_p][:20])
print("reraise spots: n=%d folds=%d calls=%d"
      % (len(rf), sum(1 for k, _, _ in rf if k == "fold"),
         sum(1 for k, _, _ in rf if k == "call")))
print("  squeeze-fold hand net sum=%+d  reraise-fold hand net sum=%+d"
      % (sum(n for k, _, n in sq if k == "fold"),
         sum(n for k, _, n in rf if k == "fold")))
