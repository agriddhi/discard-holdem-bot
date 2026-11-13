"""Test-only sparring partner: a simple but competent value bot.

Not for submission. Uses the local equity module (reuse allowed, Rulebook 10.1)
to make straightforward tight-aggressive decisions:
  - fold/call/raise by pot odds with a discount for opponent aggression
  - bet ~0.65 pot with equity >= 0.60
  - discard the highest-equity keep
This approximates what a decent opponent team might ship.
"""
import sys
import json
import random
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import equity as EQ

RANKS = "23456789TJQKA"


def hole_ids(msg_hole, fallback):
    cards = msg_hole or fallback
    return [EQ.cid(c) for c in cards], cards


def decide(msg, state):
    legal = msg.get("legal_actions") or []
    to_call = max(0, int(msg.get("to_call", 0)))
    pot = max(1, int(msg.get("pot", 0)))
    street = msg.get("street", "preflop")
    board = [EQ.cid(c) for c in (msg.get("board") or [])]
    hole = state["hole"]

    if len(hole) == 3:
        n = 400 if street == "preflop" else 500
        eqs, _ = EQ.equity_mc(hole, board, 3, n=n, per_keep=True)
        eq = float(eqs.max())
        state["eqs"] = eqs
    else:
        n = 600 if len(board) <= 4 else 0
        eq = float(EQ.equity_mc(hole, board, 2, n=max(n, 1)))
    state["eq"] = eq

    if to_call == 0:
        if "raise" in legal and eq >= 0.60:
            lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
            target = min(hi, max(lo, int(msg.get("my_bet", 0)) +
                                 round(0.65 * pot)))
            return {"type": "action", "action": "raise", "amount": int(target)}
        if "check" in legal:
            return {"type": "action", "action": "check"}
        if "raise" in legal:
            return {"type": "action", "action": "raise",
                    "amount": int(msg.get("min_raise", 2))}
        return {"type": "action", "action": "call"}

    odds = to_call / (pot + to_call)
    # rough aggression read: opponent raised this street?
    raised_opp = any(h.get("actor") == "opp" and h.get("action") == "raise"
                     and h.get("street") == street
                     for h in (msg.get("history") or []))
    eq_adj = eq - (0.10 if raised_opp else 0.0)
    if eq_adj >= odds + 0.03:
        if "raise" in legal and eq_adj >= 0.72:
            lo, hi = msg.get("min_raise", 2), msg.get("max_raise", 2)
            target = min(hi, max(lo, int(msg.get("opp_bet", 0)) +
                                 round(0.65 * (pot + to_call))))
            return {"type": "action", "action": "raise", "amount": int(target)}
        if "call" in legal:
            return {"type": "action", "action": "call"}
    if "fold" in legal:
        return {"type": "action", "action": "fold"}
    if "call" in legal:
        return {"type": "action", "action": "call"}
    return {"type": "action", "action": "check"}


def choose_discard(msg, state):
    cards = msg.get("hole_cards") or []
    board = [EQ.cid(c) for c in (msg.get("board") or [])]
    if len(cards) != 3:
        return {"type": "discard", "card": cards[0] if cards else "2s"}
    hole = [EQ.cid(c) for c in cards]
    eqs, best = EQ.equity_mc(hole, board, 3, n=500, per_keep=True)
    pairs = ((0, 1), (0, 2), (1, 2))
    a, b = pairs[best]
    keep = {a, b}
    discard = [i for i in range(3) if i not in keep][0]
    return {"type": "discard", "card": cards[discard]}


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
            _, cards = hole_ids(msg.get("hole_cards"), [])
            state["hole"] = [EQ.cid(c) for c in cards]
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
        # legality guard (action replies only)
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
        else:  # discard reply
            cards = msg.get("hole_cards") or []
            if reply.get("card") not in cards:
                reply = {"type": "discard",
                         "card": min(cards, key=lambda c: RANKS.index(c[0]))
                         if cards else "2s"}
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
