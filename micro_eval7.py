import time, numpy as np, sys
sys.path.insert(0, r"C:\Users\Gaupad\OneDrive\Dokumen\Default Project\pokerbot")
import equity

n = 6000
ranks = np.random.randint(0, 13, (n, 7))
suits = np.random.randint(0, 4, (n, 7))
NREP = 20

def t(label, fn):
    fn()  # warm
    t0 = time.perf_counter()
    for _ in range(NREP): fn()
    print(f"{label}: {(time.perf_counter()-t0)/NREP*1000:.2f} ms")

def block_rank():
    rank_oh = (ranks[:, :, None] == np.arange(13))
    return rank_oh.sum(1)
rc = block_rank()
t("rank_oh+sum", block_rank)

t("suit counts", lambda: (suits[:, :, None] == np.arange(4)).sum(1))
pr = rc > 0
sc = (suits[:, :, None] == np.arange(4)).sum(1)
flush = sc.max(1) >= 5
fs = sc.argmax(1)
in_flush = (suits == fs[:, None]) & flush[:, None]
t("flush block", lambda: ((suits[:, :, None] == np.arange(4)).sum(1)))
rank_oh = (ranks[:, :, None] == np.arange(13))
t("fc = (rank_oh & in_flush).sum", lambda: (rank_oh & in_flush[:, :, None]).sum(1))
fc = (rank_oh & in_flush[:, :, None]).sum(1)

t("_straight_high(pr)", lambda: equity._straight_high(pr))
t("_straight_high(fc>0)", lambda: equity._straight_high(fc > 0))

ones = np.ones_like(pr)
t("_top_idx k=5 x1", lambda: equity._top_idx(ones, 5, pr))
t("_top_idx k=1 x1", lambda: equity._top_idx(rc == 4, 1, pr))
t("_top_idx k=3 x1", lambda: equity._top_idx(ones, 3, pr))
t("_top_idx x11 (typical)", lambda: (
    equity._top_idx(ones, 5, pr), equity._top_idx(fc > 0, 5, fc > 0),
    equity._top_idx(rc == 4, 1, pr), equity._top_idx(pr & (rc != 4), 1, pr),
    equity._top_idx(rc == 3, 1, pr), equity._top_idx(rc >= 2, 1, pr),
    equity._top_idx(pr & (rc != 3), 2, pr), equity._top_idx(rc == 2, 2, pr),
    equity._top_idx(ones, 1, pr), equity._top_idx(rc == 2, 1, pr),
    equity._top_idx(ones, 3, pr)))

# np.select cost
cats = [np.select([pr], [pr])] * 9
t("np.select x9", lambda: np.select(cats, cats, default=cats[-1]))

# whole eval7 for reference
t("eval7 WHOLE", lambda: equity.eval7(ranks, suits))
