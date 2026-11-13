"""Does their DISCARD choice signal the strength of their kept hand?

For every showdown we know their discard and their kept-2 percentile on
the bot's exact scale (fit_t machinery).  If throwing a HIGH card means
they kept a pair/stronger holding, we can condition our betting
threshold t on the discard height we saw before the flop action.

Usage: py -3.11 dis_an.py [seat A|B] [glob ...]
"""
import re
import sys
import glob
import numpy as np

sys.path.insert(0, ".")
from equity import cid, _best_scores  # noqa: E402

RANKS = "23456789TJQKA"
SUITS = "shdc"
DECK = [r + s for r in RANKS for s in SUITS]
RV = {r: i + 2 for i, r in enumerate(RANKS)}

hand_re = re.compile(
    r"button (\w) \| \w: ([\w ]+?)  \w: ([\w ]+?) \| board ([\w ]+?) \|"
    r"(?: discards \w:(\S+) \w:(\S+))?")
act_re = re.compile(r"\b([AB])([fxcr])(\d*)")

us = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("A", "B") else "A"
pats = [a for a in sys.argv[2:] if a not in ("A", "B")] or ["logs_st*/match.log"]
files = sorted({f for p in pats for f in glob.glob(p) if "smoke" not in f})

# discard-rank bucket -> behavior -> [percentiles]
BUCKETS = [("low (2-5)", 2, 5), ("mid (6-9)", 6, 9), ("high (T-A)", 10, 14)]
data = {b[0]: {"open": [], "rr": [], "call": [], "any": []}
        for b in BUCKETS}
n_hands = {b[0]: 0 for b in BUCKETS}


def bucket(rank):
    for name, lo, hi in BUCKETS:
        if lo <= rank <= hi:
            return name
    return None


def percentile(kept, board, discards):
    known = set(kept) | set(board) | set(discards)
    deck = [c for c in DECK if c not in known]
    ids = np.array([cid(c) for c in deck], dtype=np.int64)
    ii, jj = np.triu_indices(len(ids), 1)
    opp = np.stack([ids[ii], ids[jj]], 1)
    b = np.array([cid(c) for c in board], dtype=np.int64)
    opp_s = _best_scores(opp, np.broadcast_to(b, (len(opp), 5)))
    mine = float(_best_scores(
        np.array([[cid(c) for c in kept]], dtype=np.int64), b[None, :])[0])
    return float((opp_s < mine).mean() + 0.5 * (opp_s == mine).mean())


for path in files:
    me = us
    opp_seat = "B" if me == "A" else "A"
    for line in open(path, encoding="utf-8"):
        if "showdown" not in line or "discards" not in line:
            continue
        m = hand_re.search(line)
        if not m:
            continue
        button, dealt0, dealt1, board_s, d0, d1 = m.groups()
        board = board_s.split()
        if len(board) != 5 or not d0:
            continue
        other = "B" if button == "A" else "A"
        dealt = {button: dealt0.split(), other: dealt1.split()}
        disc = {button: d0, other: d1}
        kept = {s: [c for c in dealt[s] if c != disc[s]] for s in dealt}
        if any(len(v) != 2 for v in kept.values()):
            continue

        body = line.split("|")
        acts = " ".join(body[3:-1]) if len(body) >= 5 else ""
        parts = re.split(r"\b(preflop|flop|turn|river):", acts)
        segs = [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]

        tags = set()
        last = {"A": None, "B": None}
        for street, seg in segs:
            last = {"A": None, "B": None}
            for seat, a, amt in act_re.findall(seg):
                other_s = "B" if seat == "A" else "A"
                if seat == opp_seat:
                    if a == "r":
                        tags.add("rr" if last[other_s] == "r" else "open")
                    elif a == "c" and last[other_s] == "r":
                        tags.add("call")
                last[seat] = a
        if not tags:
            continue

        bk = bucket(RV[disc[opp_seat][0]])
        if bk is None:
            continue
        n_hands[bk] += 1
        p = percentile(kept[opp_seat], board, [d0, d1])
        for tag in tags:
            data[bk][tag].append(p)
        data[bk]["any"].append(p)

print(f"files: {len(files)}  us={us}")
print(f"{'discard':<12} {'hands':>6} {'open n':>7} {'open p':>8} "
      f"{'rr n':>5} {'rr p':>7} {'call n':>7} {'call p':>8} {'any p':>8}")
for name, _, _ in BUCKETS:
    d = data[name]
    def mp(k):
        v = d[k]
        return f"{sum(v)/len(v):8.3f}" if v else f"{'-':>8}"
    print(f"{name:<12} {n_hands[name]:>6} {len(d['open']):>7} {mp('open')} "
          f"{len(d['rr']):>5} {mp('rr')} {len(d['call']):>7} {mp('call')} "
          f"{mp('any')}")

# also: how often do they discard high at all?
tot = sum(n_hands.values())
if tot:
    print("\ndiscard distribution (showdowns with bets):")
    for name, _, _ in BUCKETS:
        print(f"  {name:<12} {n_hands[name]:>5}  ({100 * n_hands[name] / tot:.1f}%)")
