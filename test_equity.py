"""Validate equity.eval7 against engine.best_hand + time equity_mc."""
import random, time, sys
sys.path.insert(0, r"C:\Users\Gaupad\OneDrive\Dokumen\Default Project\pokerbot")
import engine
import equity

RANKS = engine.RANKS
SUITS = engine.SUITS

def ref_score(cards7):
    """Official: best of C(7,5) using engine.rank5, packed like ours (rank indices)."""
    from itertools import combinations
    best = max(engine.rank5(c) for c in combinations(cards7, 5))
    cat = best[0]
    tbs = [t - 2 for t in best[1:]]          # poker value -> rank index
    tbs += [0] * (5 - len(tbs))
    s = cat
    for t in tbs:
        s = s * 16 + t
    return s

random.seed(42)
bad = 0
t0 = time.perf_counter()
N = 3000
for _ in range(N):
    cards = random.sample([r + s for r in RANKS for s in SUITS], 7)
    ranks = [RANKS.index(c[0]) for c in cards]
    suits = [SUITS.index(c[1]) for c in cards]
    import numpy as np
    got = int(equity.eval7(np.array([ranks]), np.array([suits]))[0])
    want = ref_score(cards)
    if got != want:
        bad += 1
        if bad <= 5:
            print("MISMATCH", cards, "got", got, "want", want)
t1 = time.perf_counter()
print(f"eval7: {N} hands, {bad} mismatches, {(t1-t0)/N*1000:.3f} ms/hand")

# ordering check: random pairs must agree
import numpy as np
dis = 0
for _ in range(2000):
    a = random.sample([r + s for r in RANKS for s in SUITS], 7)
    b = [c for c in [r + s for r in RANKS for s in SUITS] if c not in a]
    b = random.sample(b, 7)
    def to_arr(cs):
        return (np.array([[RANKS.index(c[0]) for c in cs]]),
                np.array([[SUITS.index(c[1]) for c in cs]]))
    sa = int(equity.eval7(*to_arr(a))[0]); sb = int(equity.eval7(*to_arr(b))[0])
    ra, rb = ref_score(a), ref_score(b)
    if (sa > sb) != (ra > rb) or (sa == sb) != (ra == rb):
        dis += 1
print(f"ordering: 2000 pairs, {dis} disagreements")

# timing equity_mc
def bench(label, my, board, opp_n, n=6000, per_keep=False):
    t0 = time.perf_counter()
    reps = 10
    for _ in range(reps):
        equity.equity_mc(my, board, opp_n, n=n, per_keep=per_keep)
    dt = (time.perf_counter() - t0) / reps * 1000
    eq = equity.equity_mc(my, board, opp_n, n=n, per_keep=per_keep)
    print(f"{label}: {dt:.1f} ms -> {eq if isinstance(eq, float) else (eq[0].round(3), eq[1])}")

bench("preflop AAx vs 3", [equity.cid("As"), equity.cid("Ad"), equity.cid("7c")], [], 3, n=1000)
bench("flop 3-card vs 3", [equity.cid("As"), equity.cid("Ad"), equity.cid("7c")],
      [equity.cid("Ah"), equity.cid("Kd"), equity.cid("2c")], 3, n=1000, per_keep=True)
bench("turn 2-card vs 2", [equity.cid("As"), equity.cid("Ad")],
      [equity.cid("Ah"), equity.cid("Kd"), equity.cid("2c"), equity.cid("9s")], 2, n=1500)
bench("river 2-card vs 2 EXACT", [equity.cid("As"), equity.cid("Ad")],
      [equity.cid("Ah"), equity.cid("Kd"), equity.cid("2c"), equity.cid("9s"), equity.cid("3d")], 2)
