"""Strong reference opponent (TEST ONLY -- never submit this).

value_bot is passive; against it we are 4x above the official scoring
cap, so it can no longer expose any leak.  This bot is built to be a
real challenge:

  * range-aware equity: it converts its raw equity into equity against
    OUR betting range (we bet with percentile >= t), instead of calling
    down on raw equity
  * preflop: opens top ~25%, 3-bets our opens top ~14%, calls tighter
    vs our aggression, and iso-raises our limps
  * postflop: value bets scaled by equity, bluffs at a frequency that
    makes us indifferent, and calls with range-adjusted equity
  * re-raises our bets when it has the nuts

Tuned by iterating against bot.py (see tune_tough.py).
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import equity as EQ  # noqa: E402

RANKS = "23456789TJQKA"

# --- our (opponent's) range thresholds: percentile >= t of the range
# that takes the given action against this bot
T_THEIR_OPEN = 0.62      # our open bet / raise
T_THEIR_CALL = 0.30      # our limp / call (wide)
T_THEIR_RERAISE = 0.80   # our re-raise


def their_range_eq(p, t):
    """Equity of a hand at percentile p against a range that bets >= t."""
    if t <= 0.02:
        return p
    return max(0.0, (p - t) / (1.0 - t))


def decide(msg, state):
    legal = msg.get("legal_actions") or []
    to_call = max(0, int(msg.get("to_call", 0)))
    pot = max(1, int(msg.get("pot", 0)))
    street = msg.get("street", "preflop")
    board = [EQ.cid(c) for c in (msg.get("board") or [])]
    hole = state["hole"]

    if len(hole) == 3:
        eqs, _ = EQ.equity_mc(hole, board, 3, n=350, per_keep=True)
        eq = float(eqs.max())
    else:
        eq = float(EQ.equity_mc(hole, board, 2, n=500))
    state["eq"] = eq

    # did they raise or just bet on this street?
    hist = msg.get("history") or []
    their_raise = any(h.get("actor") == "opp" and h.get("action") == "raise"
                      and h.get("street") == street for h in hist)
    their_bet = any(h.get("actor") == "opp" and h.get("action") in
                     ("raise", "bet") and h.get("street") == street
                     for h in hist)
    # our re-raise over their raise?
    their_rr = False
    prev = None
    for h in hist:
        if h.get("street") != street:
            prev = None
            continue
        if h.get("actor") == "opp" and h.get("action") == "raise" \
                and prev == "raise":
            their_rr = True
        prev = h.get("action") if h.get("actor") == "me" else None

    if street == "preflop":
        if to_call == 0:
            # open: top ~25%
            if "raise" in legal and eq >= 0.60:
                lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
                target = min(hi, max(lo, 8))
                return {"type": "action", "action": "raise",
                        "amount": int(target)}
            if "check" in legal:
                return {"type": "action", "action": "check"}
            return {"type": "action", "action": "call"}
        odds = to_call / (pot + to_call)
        if their_raise:
            # their open is a strong range; 3-bet the top, call the rest
            if "raise" in legal and eq >= 0.74:
                lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
                target = min(hi, max(lo, int(msg.get("opp_bet", 0)) + 16))
                return {"type": "action", "action": "raise",
                        "amount": int(target)}
            need = their_range_eq(eq, T_THEIR_OPEN) >= odds + 0.02
            if need and "call" in legal:
                return {"type": "action", "action": "call"}
            if "call" in legal:
                return {"type": "action", "action": "call"}
            return {"type": "action", "action": "check"}
        # they limped: iso-raise the top, call cheap, fold the junk
        if "raise" in legal and eq >= 0.72:
            lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
            target = min(hi, max(lo, int(msg.get("opp_bet", 0)) + 10))
            return {"type": "action", "action": "raise", "amount": int(target)}
        odds = to_call / (pot + to_call)
        if eq >= odds + 0.02 and "call" in legal:
            return {"type": "action", "action": "call"}
        if "call" in legal:
            return {"type": "action", "action": "call"}
        return {"type": "action", "action": "check"}

    # ---------------- postflop ----------------
    odds = to_call / (pot + to_call)
    if to_call == 0:
        # value bet scaled by equity; bluff a fraction of the weak range
        if "raise" in legal:
            if eq >= 0.58:
                lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
                size = 0.45 + 1.4 * (eq - 0.58)
                target = min(hi, max(lo, int(msg.get("my_bet", 0)) +
                                     round(size * pot)))
                return {"type": "action", "action": "raise",
                        "amount": int(target)}
            if eq >= 0.34 and random.random() < 0.22:
                lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
                target = min(hi, max(lo, int(msg.get("my_bet", 0)) +
                                     round(0.55 * pot)))
                return {"type": "action", "action": "raise",
                        "amount": int(target)}
        if "check" in legal:
            return {"type": "action", "action": "check"}
        return {"type": "action", "action": "call"}

    # facing a bet: adjust for their range
    t = T_THEIR_RERAISE if their_rr else T_THEIR_OPEN
    eq_r = their_range_eq(eq, t)
    if their_rr:
        if "raise" in legal and eq >= 0.80:
            lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
            target = min(hi, max(lo, int(msg.get("opp_bet", 0)) +
                                 round(0.9 * (pot + to_call))))
            return {"type": "action", "action": "raise", "amount": int(target)}
        if eq_r >= odds + 0.02 and "call" in legal:
            return {"type": "action", "action": "call"}
    else:
        if "raise" in legal and eq >= 0.80:
            lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
            target = min(hi, max(lo, int(msg.get("opp_bet", 0)) +
                                 round(0.9 * (pot + to_call))))
            return {"type": "action", "action": "raise", "amount": int(target)}
        if eq_r >= odds + 0.02 and "call" in legal:
            return {"type": "action", "action": "call"}
    if "call" in legal:
        return {"type": "action", "action": "call"}
    return {"type": "action", "action": "check"}


def choose_discard(msg, state):
    cards = msg.get("hole_cards") or []
    if len(cards) != 3:
        return {"type": "discard", "card": cards[0] if cards else "2s"}
    hole = [EQ.cid(c) for c in cards]
    eqs, best = EQ.equity_mc(hole, [EQ.cid(c) for c in
                                    (msg.get("board") or [])], 3, n=400,
                             per_keep=True)
    a, b = ((0, 1), (0, 2), (1, 2))[best]
    keep = {a, b}
    drop = [i for i in range(3) if i not in keep][0]
    return {"type": "discard", "card": cards[drop]}


def main():
    state = {"hole": [], "eq": 0.5}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        t = msg.get("type")
        if t == "match_end":
            break
        if t == "new_hand":
            state["hole"] = [EQ.cid(c) for c in (msg.get("hole_cards") or [])]
            continue
        if t == "discard_result":
            state["hole"] = [EQ.cid(c) for c in (msg.get("hole_cards") or [])]
            continue
        if t == "action_request":
            hc = msg.get("hole_cards")
            if hc:
                state["hole"] = [EQ.cid(c) for c in hc]
            reply = decide(msg, state)
        elif t == "discard_request":
            reply = choose_discard(msg, state)
        else:
            continue
        if t == "action_request":
            legal = msg.get("legal_actions") or []
            if reply.get("action") not in legal:
                reply = ({"type": "action", "action": "check"} if "check" in legal
                         else {"type": "action", "action": "call"} if "call" in legal
                         else {"type": "action", "action": "fold"})
            if reply.get("action") == "raise":
                lo = int(msg.get("min_raise", 2))
                hi = int(msg.get("max_raise", lo))
                if hi < lo:
                    hi = lo
                amt = reply.get("amount", lo)
                if not isinstance(amt, int) or isinstance(amt, bool) \
                        or not lo <= amt <= hi:
                    reply = {"type": "action", "action": "raise", "amount": int(lo)}
            if reply.get("action") == "raise" and "raise" not in legal:
                reply = {"type": "action", "action": "check"} if "check" in legal \
                    else {"type": "action", "action": "call"}
        else:
            cards = msg.get("hole_cards") or []
            if reply.get("card") not in cards:
                reply = {"type": "discard",
                         "card": min(cards, key=lambda c: RANKS.index(c[0]))
                         if cards else "2s"}
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
