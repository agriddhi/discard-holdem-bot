"""Analyze CAL lines: assumed equity vs realized result, by street."""
import sys
import glob
from collections import defaultdict

by_street = defaultdict(lambda: [0, 0.0, 0.0])   # street -> [n, eq_sum, res_sum]
river_cases = []

files = sys.argv[1:] or (glob.glob("logs_cal*/A_leg*_stderr.txt"))
for f in files:
    for line in open(f, encoding="utf-8", errors="replace"):
        if not line.startswith("CAL "):
            continue
        parts = dict(p.split("=") for p in line.split()[1:])
        eq = float(parts["eq"])
        res = float(parts["res"])
        st = parts["street"]
        net = int(parts["net"])
        by_street[st][0] += 1
        by_street[st][1] += eq
        by_street[st][2] += res
        if st == "river":
            river_cases.append((eq, res, net))

print(f"{'street':<10} {'n':>4} {'assumed':>8} {'realized':>9} {'gap':>7}")
tot = [0, 0.0, 0.0]
for st, (n, e, r) in sorted(by_street.items()):
    print(f"{st:<10} {n:>4} {e / n:>8.3f} {r / n:>9.3f} {(e - r) / n:>+7.3f}")
    tot[0] += n; tot[1] += e; tot[2] += r
if tot[0]:
    print(f"{'ALL':<10} {tot[0]:>4} {tot[1] / tot[0]:>8.3f} "
          f"{tot[2] / tot[0]:>9.3f} {(tot[1] - tot[2]) / tot[0]:>+7.3f}")

print("\nriver calls in detail (assumed -> realized):")
for eq, res, net in sorted(river_cases):
    print(f"  eq={eq:.3f} res={res:.1f} net={net:+d}")
