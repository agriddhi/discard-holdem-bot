"""Sweep the parametric opponent space to find where our bot breaks.

Each row is a plausible "competent opponent" configuration.  We report
the raw net (sensitive) and the capped net (official) per match, so we
can see whether any realistic opponent beats us.

Usage: py -3.11 sweep.py [seed] [extra seeds...]
"""
import os
import re
import subprocess
import sys

SEEDS = [int(a) for a in sys.argv[1:] if a.isdigit()] or [111]

# (label, env overrides)
CONFIGS = [
    ("value_like", {}),
    ("opens_loose", {"OPEN_EQ": "0.45"}),
    ("opens_very_loose", {"OPEN_EQ": "0.35"}),
    ("opens_tight", {"OPEN_EQ": "0.80"}),
    ("bb_aggressive", {"BB_EQ": "0.40"}),
    ("bb_very_aggressive", {"BB_EQ": "0.30"}),
    ("3bet_loose", {"RB_EQ": "0.50"}),
    ("3bet_very_loose", {"RB_EQ": "0.35"}),
    ("3bet_tight", {"RB_EQ": "0.85"}),
    ("postflop_loose", {"BET_EQ": "0.45"}),
    ("postflop_tight", {"BET_EQ": "0.75"}),
    ("calls_tight", {"CALL_ADD": "0.10"}),
    ("calls_loose", {"CALL_ADD": "0.0"}),
    ("bluffy", {"BLUFF": "0.35"}),
    ("reraises", {"RAISE_FRAC": "0.5"}),
    ("all_loose", {"OPEN_EQ": "0.40", "BB_EQ": "0.40", "RB_EQ": "0.45",
                   "BET_EQ": "0.48", "CALL_ADD": "0.0", "BLUFF": "0.3"}),
    ("all_tight", {"OPEN_EQ": "0.80", "BB_EQ": "0.75", "RB_EQ": "0.85",
                   "BET_EQ": "0.72", "CALL_ADD": "0.10"}),
]

net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")
label_re = re.compile(r"^\s*([AB])\s+(.+?)\s+net\s+([+-]\d+)")
forfeit_re = re.compile(r"Result: ([AB]) wins by forfeit")


def is_us(label):
    return label.replace("\\", "/").split("/")[-1] == "bot.py"


def run(env_over, seed):
    env = dict(os.environ)
    env.update(env_over)
    ld = f"logs_sweep_{seed}"
    cmd = ["py", "-3.11", "engine.py", "bot.py",
           "example_bots\\param_bot.py", "--seed", str(seed), "--log-dir", ld]
    out = subprocess.run(cmd, capture_output=True, text=True, env=env,
                         timeout=240).stdout
    seat = None
    raw = None
    notices = 0
    for line in out.splitlines():
        m = label_re.match(line)
        if m and is_us(m.group(2)):
            seat = m.group(1)
            raw = int(m.group(3))
        nm = re.search(r"notices (\d+)", line)
        if nm:
            notices = int(nm.group(1))
    if raw is None:
        return None, None, notices
    fm = forfeit_re.search(out)
    if fm:
        cap = 400 if fm.group(1) == seat else -400
    else:
        cap = max(-400, min(400, raw))
    return raw, cap, notices


print(f"seeds {SEEDS}")
print(f"{'config':<20} {'raw/match':>10} {'capped':>8} {'notices':>8} "
      f"{'verdict':>9}")
worst = []
for label, env_over in CONFIGS:
    raws = []
    caps = []
    nt = 0
    for seed in SEEDS:
        raw, cap, notices = run(env_over, seed)
        nt = max(nt, notices)
        if raw is None:
            continue
        raws.append(raw)
        caps.append(cap)
    if not raws:
        print(f"{label:<20} {'NO RESULT':>10}")
        continue
    ravg = sum(raws) / len(raws)
    cavg = sum(caps) / len(caps)
    verdict = "OK" if cavg > 0 else ("~0" if cavg == 0 else "LOSS")
    print(f"{label:<20} {ravg:>10.0f} {cavg:>8.0f} {nt:>8} {verdict:>9}")
    worst.append((cavg, label))

worst.sort()
print("\nweakest configs:")
for c, label in worst[:5]:
    print(f"  {label:<20} capped {c:+.0f}")
