"""Net by POSITION: when WE are the button vs when they are.

match.log line: "L1 #3    button A | A: ...  B: ... | board ... | ... | fold A +2, B -2"
The button seat is printed per hand; our seat is fixed per file (pass A/B).

Usage: py -3.11 pos_analysis.py [logs_t*/match.log ...] [A|B]
"""
import re
import sys
import glob

me = sys.argv[-1] if sys.argv[-1] in ("A", "B") else "A"
args = [a for a in sys.argv[1:] if a not in ("A", "B")]
pats = args or ["logs_t*/match.log"]
files = sorted({f for p in pats for f in glob.glob(p)})
opp = "B" if me == "A" else "A"

net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")
btn_re = re.compile(r"button (\w)")

# bucket -> [net, hands, showdown_net, showdown_n, fold_for_net, fold_for_n,
#            fold_against_net, fold_against_n]
b = {True: [0, 0, 0, 0, 0, 0, 0, 0], False: [0, 0, 0, 0, 0, 0, 0, 0]}

for path in files:
    for line in open(path, encoding="utf-8"):
        nm = net_re.search(line.rstrip())
        bm = btn_re.search(line)
        if not nm or not bm:
            continue
        net = int(nm.group(2)) if nm.group(1) == me else int(nm.group(4))
        we_btn = bm.group(1) == me
        r = b[we_btn]
        r[0] += net
        r[1] += 1
        if "showdown" in line:
            r[2] += net
            r[3] += 1
        elif re.search(r"\| fold ", line):
            if net > 0:      # they folded
                r[4] += net
                r[5] += 1
            else:            # we folded
                r[6] += net
                r[7] += 1

print(f"files: {len(files)}  (us = seat {me})")
print(f"{'we are...':<14} {'hands':>6} {'net':>8} {'avg':>7} | "
      f"{'showdown':>9} {'avg':>7} | {'they fold':>9} {'avg':>7} | "
      f"{'we fold':>8} {'avg':>7}")
for we_btn in (True, False):
    r = b[we_btn]
    lbl = "BUTTON" if we_btn else "BIG BLIND"
    so = f"{r[3]:>9} {r[2] / r[3]:>+7.2f}" if r[3] else f"{'-':>9} {'-':>7}"
    tf = f"{r[5]:>9} {r[4] / r[5]:>+7.2f}" if r[5] else f"{'-':>9} {'-':>7}"
    wf = f"{r[7]:>8} {r[6] / r[7]:>+7.2f}" if r[7] else f"{'-':>8} {'-':>7}"
    print(f"{lbl:<14} {r[1]:>6} {r[0]:>8} {r[0] / r[1]:>+7.2f} | "
          f"{so} | {tf} | {wf}")
