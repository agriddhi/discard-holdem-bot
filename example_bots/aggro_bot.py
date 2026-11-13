"""Aggro opponent (TEST ONLY): 3-bets and raises a lot.

Purpose: our local opponents (value_bot, random, starter) barely raise
preflop, so they cannot expose a leak in how we handle pressure.  This
bot 3-bets our opens, raises our limps, and applies constant pressure,
which is where a strong opponent would attack our wide small-blind
limp range.

Usage: engine.py bot.py example_bots/aggro_bot.py --seed 1
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import equity as EQ  # noqa: E402

RANKS = "23456789TJQKA"


def decide(msg, state):
    legal = msg.get("legal_actions") or []
    to_call = max(0, int(msg.get("to_call", 0)))
    pot = max(1, int(msg.get("pot", 0)))
    street = msg.get("street", "preflop")
    board = [EQ.cid(c) for c in (msg.get("board") or [])]
    hole = state["hole"]

    if len(hole) == 3:
        eqs, _ = EQ.equity_mc(hole, board, 3, n=300, per_keep=True)
        eq = float(eqs.max())
    else:
        eq = float(EQ.equity_mc(hole, board, 2, n=400))
    state["eq"] = eq

    hist = msg.get("history") or []
    their_raise = any(h.get("actor") == "opp" and h.get("action") == "raise"
                      and h.get("street") == street for h in hist)

    if street == "preflop":
        if to_call == 0:
            if "raise" in legal and eq >= 0.52:
                lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
                return {"type": "action", "action": "raise",
                        "amount": int(min(hi, max(lo, 8)))}
            if "check" in legal:
                return {"type": "action", "action": "check"}
            return {"type": "action", "action": "call"}
        odds = to_call / (pot + to_call)
        # 3-bet our opens wide (top ~22%), and re-raise our raises
        if their_raise:
            if "raise" in legal and eq >= 0.60:
                lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
                target = min(hi, max(lo, int(msg.get("opp_bet", 0)) + 18))
                return {"type": "action", "action": "raise",
                        "amount": int(target)}
            if eq >= odds + 0.04 and "call" in legal:
                return {"type": "action", "action": "call"}
        else:
            # they limped: iso-raise wide (top ~30%)
            if "raise" in legal and eq >= 0.58:
                lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
                target = min(hi, max(lo, int(msg.get("opp_bet", 0)) + 8))
                return {"type": "action", "action": "raise",
                        "amount": int(target)}
            if eq >= odds + 0.02 and "call" in legal:
                return {"type": "action", "action": "call"}
        if "call" in legal:
            return {"type": "action", "action": "call"}
        return {"type": "action", "action": "check"}

    odds = to_call / (pot + to_call)
    if to_call == 0:
        if "raise" in legal and eq >= 0.52:
            lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
            target = min(hi, max(lo, int(msg.get("my_bet", 0)) +
                                 round(0.7 * pot)))
            return {"type": "action", "action": "raise", "amount": int(target)}
        if eq >= 0.30 and random.random() < 0.30:
            lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
            target = min(hi, max(lo, int(msg.get("my_bet", 0)) +
                                 round(0.6 * pot)))
            return {"type": "action", "action": "raise", "amount": int(target)}
        if "check" in legal:
            return {"type": "action", "action": "check"}
        return {"type": "action", "action": "call"}
    if their_raise and "raise" in legal and eq >= 0.74:
        lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
        target = min(hi, max(lo, int(msg.get("opp_bet", 0)) +
                             round(0.85 * (pot + to_call))))
        return {"type": "action", "action": "raise", "amount": int(target)}
    if eq >= odds + 0.03 and "call" in legal:
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
                                    (msg.get("board") or [])], 3, n=350,
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
