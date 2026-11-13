"""Robust parser for engine match.log lines.

Line format (engine.py log_hand):

  L{leg+1} #{id:<4} button {n0} | {n0}: c1 c2 c3  {n1}: d1 d2 d3 |
  board b1 .. b5 | discards {n0}:{card} {n1}:{card} | {acts} |
  {result}[ (hand names)] {n0} {net0:+d}, {n1} {net1:+d}

The line is split on '|' into segments; the discards segment is optional.
"""
import re

ACT_RE = re.compile(r"\b([AB])([fxcr])(\d*)")
DISC_RE = re.compile(r"([AB]):(\S+)")
NET_RE = re.compile(r"([AB])\s+([+-]\d+)\s*,\s*([AB])\s+([+-]\d+)")


def parse(line):
    """-> dict with the hand's fields, or None if the line is not a hand."""
    if not line.startswith("L") or "|" not in line:
        return None
    segs = line.split("|")
    if len(segs) < 5:
        return None
    m = re.match(r"^L(\d+)\s+#(\d+)\s+button\s+([AB])", segs[0].strip())
    if not m:
        return None
    sm = re.search(r"([AB]):\s+(.*?)\s+([AB]):\s+(.*)", segs[1])
    if not sm:
        return None
    board = segs[2].replace("board", "", 1).split()
    idx = 3
    disc = {}
    if segs[idx].strip().startswith("discards"):
        for seat, card in DISC_RE.findall(segs[idx]):
            disc[seat] = card
        idx += 1
    acts_seg = segs[idx]
    tail = segs[idx + 1] if idx + 1 < len(segs) else ""
    acts = []
    street = None
    for tok in acts_seg.split():
        if tok.endswith(":"):
            street = tok[:-1]
            continue
        a = ACT_RE.fullmatch(tok)
        if a:
            acts.append((street, a.group(1), a.group(2),
                         int(a.group(3)) if a.group(3) else None))
    net = {}
    nm = NET_RE.search(tail)
    if nm:
        net[nm.group(1)] = int(nm.group(2))
        net[nm.group(3)] = int(nm.group(4))
    result = tail.split()[0] if tail.split() else ""
    return {
        "leg": int(m.group(1)),
        "hid": int(m.group(2)),
        "btn": m.group(3),
        "seats": (sm.group(1), sm.group(3)),
        "dealt": (sm.group(2).split(), sm.group(4).split()),
        "board": board,
        "discards": disc,
        "acts": acts,
        "result": result,
        "net": net,
    }


def our_label(path_lines):
    """Our seat label ('A'/'B') from the summary lines naming bot.py."""
    for line in path_lines:
        m = re.match(r"^\s*([AB])\s+(.+?)\s+net\s+", line)
        if m and m.group(2).replace("\\", "/").split("/")[-1] == "bot.py":
            return m.group(1)
    return None


if __name__ == "__main__":
    import glob
    import sys
    ok = bad = 0
    for f in sorted(glob.glob("logs_st*/match.log") + glob.glob("logs_rd*/match.log")):
        if "smoke" in f or "stage" in f:
            continue
        for line in open(f, encoding="utf-8"):
            if line.startswith("L") and "|" in line:
                if parse(line):
                    ok += 1
                else:
                    bad += 1
    print(f"parsed {ok}, failed {bad}")
