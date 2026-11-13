import time, sys, numpy as np
sys.path.insert(0, r"C:\Users\Gaupad\OneDrive\Dokumen\Default Project\pokerbot")
import equity

for n in (1000, 2000, 6000):
    ranks = np.random.randint(0, 13, (n, 7)); suits = np.random.randint(0, 4, (n, 7))
    equity.eval7(ranks, suits)
    t0 = time.perf_counter()
    for _ in range(10): equity.eval7(ranks, suits)
    print(f"eval7 N={n}: {(time.perf_counter()-t0)/10*1000:.2f} ms")

for n in (2000, 6000):
    t0 = time.perf_counter()
    for _ in range(10):
        samp = np.arange(52)[np.argsort(np.random.random((n, 49)), axis=1)[:, :8]]
    print(f"sample N={n}: {(time.perf_counter()-t0)/10*1000:.2f} ms")

n = 6000
board = np.random.randint(0, 52, (n, 5))
ids3 = np.random.randint(0, 52, (n, 3))
ids2 = np.random.randint(0, 52, (n, 2))
t0 = time.perf_counter()
for _ in range(6): equity._best_scores(ids3, board)
print(f"_best_scores(3card, x3 eval7) N=6000: {(time.perf_counter()-t0)/6*1000:.2f} ms")
t0 = time.perf_counter()
for _ in range(6): equity._best_scores(ids2, board)
print(f"_best_scores(2card) N=6000: {(time.perf_counter()-t0)/6*1000:.2f} ms")

# where inside eval7? time the _top_idx calls
n = 6000
ranks = np.random.randint(0, 13, (n, 7)); suits = np.random.randint(0, 4, (n, 7))
rank_oh = (ranks[:, :, None] == np.arange(13))
rc = rank_oh.sum(1)
pr = rc > 0
t0 = time.perf_counter()
for _ in range(20):
    equity._top_idx(np.ones_like(pr), 5, pr)
print(f"_top_idx k=5: {(time.perf_counter()-t0)/20*1000:.2f} ms")
