"""Does their bet SIZE predict strength?  Bucket CAL samples by the pot odds
we faced and show the realized win rate in each bucket."""
import sys
import glob
import re
from collections import defaultdict

pat = re.compile(r"eq=(\S+) res=(\S+) street=(\S+) odds=(\S+)")
buckets = defaultdict(lambda: [0, 0.0, 0.0])   # odds bucket -> [n, eq, res]

files = [f for a in (sys.argv[1:] or ["logs_t*/A_leg*_stderr.txt",
                                      "logs_c*/A_leg*_stderr.txt"])
         for f in glob.glob(a)]
for f in files:
    for line in open(f, encoding="utf-8", errors="replace"):
        m = pat.search(line)
        if not m:
            continue
        eq, res, odds = float(m.group(1)), float(m.group(2)), float(m.group(4))
        b = round(min(odds, 0.75) * 4) / 4      # 0, .25, .5, .75+
        buckets[b][0] += 1
        buckets[b][1] += eq
        buckets[b][2] += res

print(f"{'odds faced':>10} {'n':>4} {'assumed':>8} {'realized':>9} {'gap':>7}")
for b in sorted(buckets):
    n, e, r = buckets[b]
    print(f"{b:>10.2f} {n:>4} {e / n:>8.3f} {r / n:>9.3f} {(e - r) / n:>+7.3f}")
