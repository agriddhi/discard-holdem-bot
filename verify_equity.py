"""Independently verify CAL river equities via brute force + official rank5.

Reads CAL lines from a stderr log, recomputes exact equity by enumerating
every opponent holding with engine.rank5 (no numpy, no eval7), and compares.
"""
import sys
import itertools
import re

sys.path.insert(0, ".")
from engine import rank5, best_hand

RANKS = "23456789TJQKA"
SUITS = "shdc"
ALL_CARDS = [r + s for r in RANKS for s in SUITS]


def cid(c):
    return RANKS.index(c[0]) * 4 + SUITS.index(c[1])


def verify(hole, board, out, target):
    known = set(hole) | set(board) | set(out)
    deck = [c for c in ALL_CARDS if c not in known]
    # our best hand from exactly 5 board + 2 hole
    my_score = best_hand(hole, board)
    wins = ties = 0
    total = 0
    for a, b in itertools.combinations(deck, 2):
        opp = [a, b]
        o = best_hand(opp, board)
        total += 1
        if my_score > o:
            wins += 1
        elif my_score == o:
            ties += 1
    eq = (wins + 0.5 * ties) / total
    return eq, total


pat = re.compile(r"eq=(\S+) res=(\S+) street=(\S+) net=(-?\d+) hid=(\d+) "
                 r"hole=(\S+) board=(\S+) out=(\S*)")

bad = checked = 0
for path in sys.argv[1:]:
    for line in open(path, encoding="utf-8", errors="replace"):
        m = pat.search(line)
        if not m:
            continue
        if m.group(3) != "river":
            continue
        target = float(m.group(1))
        hole = m.group(6).split(",")
        board = m.group(7).split(",")
        out = [c for c in m.group(8).split(",") if c]
        if len(board) != 5 or len(hole) != 2:
            continue
        eq, n = verify(hole, board, out, target)
        checked += 1
        flag = "OK " if abs(eq - target) < 0.01 else "BAD"
        if flag == "BAD":
            bad += 1
        print(f"{flag} hid={m.group(5):>3} reported={target:.3f} "
              f"bruteforce={eq:.3f} (n={n}) hole={hole} board={board}")

print(f"\nchecked {checked}, mismatched {bad}")
