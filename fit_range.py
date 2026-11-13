"""Fit the range model on CAL data.

Model: on a fixed board, hand strength is a total order, so "equity vs random"
p IS the hand's percentile. If the opponent only bets hands with percentile
>= t, our equity vs their range is:

    realized = (p - t) / (1 - t)      for p > t

Rewriting with u = 1/(1-t):  realized = 1 - u*(1-p)  -> linear in (1-p).

Fit u by least squares through the origin on (1-res) vs (1-p).
"""
import sys
import glob
import re

pat = re.compile(r"eq=(\S+) res=(\S+) street=(\S+)")

samples = []          # (p, res, street)
for f in (sys.argv[1:] or glob.glob("logs_cal*/A_leg*_stderr.txt")
          + glob.glob("logs_vfy/A_leg*_stderr.txt")):
    for line in open(f, encoding="utf-8", errors="replace"):
        m = pat.search(line)
        if m:
            samples.append((float(m.group(1)), float(m.group(2)), m.group(3)))

print(f"samples: {len(samples)}")

# fit u on all samples
num = sum((1 - p) * (1 - r) for p, r, _ in samples)
den = sum((1 - p) ** 2 for p, r, _ in samples)
u = num / den if den else 1.0
t = 1 - 1 / u
print(f"fit u={u:.3f}  ->  implied betting threshold t={t:.3f}")

# fit river-only (cleanest: no future cards, exact p)
riv = [(p, r) for p, r, s in samples if s == "river"]
if len(riv) >= 10:
    num = sum((1 - p) * (1 - r) for p, r in riv)
    den = sum((1 - p) ** 2 for p, r in riv)
    u2 = num / den
    print(f"river-only: n={len(riv)} u={u2:.3f} -> t={1 - 1 / u2:.3f}")

# fit per-street
for st in ("preflop", "flop", "turn", "river"):
    sub = [(p, r) for p, r, s in samples if s == st]
    if len(sub) >= 8:
        num = sum((1 - p) * (1 - r) for p, r in sub)
        den = sum((1 - p) ** 2 for p, r in sub)
        u3 = num / den
        print(f"  {st:<8} n={len(sub):>3} u={u3:.3f} t={1 - 1 / u3:.3f}")

# how well does the fit explain the data? compare binned
print("\nbinned check (all samples):")
buckets = {}
for p, r, _ in samples:
    b = round(p * 10) / 10
    buckets.setdefault(b, []).append(r)
print(f"{'p bin':>6} {'n':>4} {'observed':>9} {'predicted':>9}")
for b in sorted(buckets):
    v = buckets[b]
    pred = max(0.0, min(1.0, 1 - u * (1 - b)))
    print(f"{b:>6.1f} {len(v):>4} {sum(v) / len(v):>9.3f} {pred:>9.3f}")

# residual with constant-gap alternative (what's currently implemented)
const_gap = sum(p - r for p, r, _ in samples) / len(samples)
err_const = sum(abs((p - const_gap) - r) for p, r, _ in samples) / len(samples)
err_model = sum(abs(max(0.0, min(1.0, 1 - u * (1 - p))) - r)
                for p, r, _ in samples) / len(samples)
print(f"\nmean abs error  constant-gap({const_gap:.3f}): {err_const:.3f}")
print(f"mean abs error  range-model(u={u:.3f}):      {err_model:.3f}")
