"""Fit the opponent's betting thresholds t offline from match.log.

For every showdown we know their final 2 cards, the board and both exposed
discards, so we can compute the percentile of their hand on the same scale
the bot uses: vs a random holding from the 43 cards left after their hand,
the board and the discards.  Classifying what each seat DID:

    open   – raised with no raise of theirs in front (open bet / barrel)
    rr     – raised immediately after the other seat's raise (re-raise)
    call   – called facing the other seat's raise

grouped by street group (river vs earlier) gives the mean percentile of
each part of their range -> implied threshold t = 2*mean - 1.

Which seat is "us" matters (we must not mix our own range into the
opponent's pool), so each file may carry a :SEAT suffix:

    py -3.11 fit_t.py A logs_t111/match.log logs_t222/match.log
    py -3.11 fit_t.py B logs_t333/match.log
"""
import re
import sys
import glob
import numpy as np

sys.path.insert(0, ".")
from equity import cid, _best_scores

RANKS = "23456789TJQKA"
SUITS = "shdc"
DECK = [r + s for r in RANKS for s in SUITS]

hand_re = re.compile(
    r"button (\w) \| \w: ([\w ]+?)  \w: ([\w ]+?) \| board ([\w ]+?) \|"
    r"(?: discards \w:(\S+) \w:(\S+))?")
act_re = re.compile(r"\b([AB])([fxcr])(\d*)")

us = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("A", "B") else "A"
pats = [a for a in sys.argv[2:] if not a.endswith(":A") and not a.endswith(":B")]
pats += [a.rsplit(":", 1)[0] for a in sys.argv[1:]
         if a.endswith(":A") or a.endswith(":B")]
if not pats:
    pats = ["logs_t*/match.log"]
files = sorted({f for p in pats for f in glob.glob(p)})

# per-file seat override: "path:B" -> seat of OUR bot in that file
overrides = {}
for a in sys.argv[1:]:
    if a.endswith(":A") or a.endswith(":B"):
        p, s = a.rsplit(":", 1)
        for f in glob.glob(p):
            overrides[f] = s

pools = {"open_r": [], "open_e": [], "rr_r": [], "rr_e": [],
         "call_r": [], "call_e": [],
         "open_p": [], "rr_p": [], "call_p": []}


def percentile(kept, board, discards):
    """Percentile of `kept` vs a random holding (bot's exact scale)."""
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
    me = overrides.get(path, us)
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

        tags = set()                     # (behavior, street) shown by opp
        last = {"A": None, "B": None}    # each seat's last action this street
        for street, seg in segs:
            last = {"A": None, "B": None}
            for seat, a, amt in act_re.findall(seg):
                other_s = "B" if seat == "A" else "A"
                if seat == opp_seat:
                    if a == "r":
                        tags.add(("rr" if last[other_s] == "r" else "open",
                                  street))
                    elif a == "c" and last[other_s] == "r":
                        tags.add(("call", street))
                last[seat] = a
        if not tags:
            continue

        p = percentile(kept[opp_seat], board, [d0, d1])
        for tag, street in tags:
            if street == "river":
                key = tag + "_r"
            elif street == "preflop":
                key = tag + "_p"
            else:
                key = tag + "_e"
            pools[key].append(p)

print(f"files: {len(files)}  us={us} overrides={len(overrides)}")
print(f"{'pool':<10} {'n':>5} {'mean p':>8} {'t=2m-1':>8}")
for k in ("open_p", "open_e", "open_r", "rr_p", "rr_e", "rr_r",
          "call_p", "call_e", "call_r"):
    v = pools[k]
    if v:
        m = sum(v) / len(v)
        print(f"{k:<10} {len(v):>5} {m:>8.3f} {2 * m - 1:>+8.3f}")
