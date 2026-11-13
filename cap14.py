"""Official (capped) scoring: per-match our_net, then clamp to +/-400 (stage 1).

Auto-detects which seat we are from the summary label line (bot.py).
Usage: py -3.11 cap14.py [prefix ...] [-v]
"""
import re
import sys
import glob

CAP = 400  # stage 1
net_re = re.compile(r"([AB]) ([+-]\d+), ([AB]) ([+-]\d+)\s*$")
label_re = re.compile(r"^\s*([AB])\s+(.+?)\s+net\s+([+-]\d+)")
forfeit_re = re.compile(r"Result: ([AB]) wins by forfeit")


def is_us(label):
    return label.replace("\\", "/").split("/")[-1] == "bot.py"


def score(prefix):
    raw = cap = 0
    n = beyond = 0
    rows = []
    for f in sorted(glob.glob(prefix + "*/match.log")):
        if "smoke" in f:
            continue
        txt = open(f, encoding="utf-8").read()
        seat = None
        our_raw = None
        for line in txt.splitlines():
            m = label_re.match(line)
            if m and is_us(m.group(2)):
                seat = m.group(1)
                our_raw = int(m.group(3))
        if seat is None or our_raw is None:
            print(f"  !! could not detect our seat in {f}")
            continue
        fm = forfeit_re.search(txt)
        if fm:
            our_cap = CAP if fm.group(1) == seat else -CAP
        else:
            our_cap = max(-CAP, min(CAP, our_raw))
        seed = re.search(r"(\d+)", f).group(1)
        rows.append((seed, seat, our_raw, our_cap))
        raw += our_raw
        cap += our_cap
        n += 1
        if abs(our_raw) > CAP:
            beyond += 1
    print(f"{prefix:10s} matches={n:3d} raw={raw:+7d} capped={cap:+7d} "
          f"(beyond cap: {beyond})")
    return rows


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:] if a != "-v"]
    verbose = "-v" in sys.argv[1:]
    prefixes = argv or ["logs_t", "logs_rr", "logs_b1", "logs_rd"]
    for p in prefixes:
        rows = score(p)
        if verbose:
            for seed, seat, r, c in rows:
                flag = " CAPPED" if abs(r) > CAP else ""
                print(f"   seed {seed:>10} seat {seat}: raw {r:+6d}  "
                      f"capped {c:+5d}{flag}")
        print()
