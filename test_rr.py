"""Unit tests for the batch-A helpers: _opp_raises / _facing_reraise."""
import sys
sys.path.insert(0, ".")
from bot import _opp_raises, _facing_reraise, _opp_raised


def h(street, actor, action, amount=None):
    e = {"street": street, "actor": actor, "action": action}
    if amount is not None:
        e["amount"] = amount
    return e


cases = [
    # (name, history, street, exp_facing_rr, exp_raises)
    ("open bet by opp, we never raised",
     [h("flop", "opp", "raise", 3)],
     "flop", False, {("open", "flop")}),

    ("we raise, they re-raise",
     [h("flop", "me", "raise", 3), h("flop", "opp", "raise", 9)],
     "flop", True, {("rr", "flop")}),

    ("we raise, they call (no rr)",
     [h("flop", "me", "raise", 3), h("flop", "opp", "call", 3)],
     "flop", False, set()),

    ("open, we 3-bet, they 4-bet",
     [h("preflop", "opp", "raise", 6), h("preflop", "me", "raise", 18),
      h("preflop", "opp", "raise", 40)],
     "preflop", True, {("rr", "preflop"), ("open", "preflop")}),

    ("they raise NEXT street after our raise (new street -> open)",
     [h("flop", "me", "raise", 3), h("turn", "opp", "raise", 8)],
     "turn", False, {("open", "turn")}),

    ("they open each street (barrel)",
     [h("flop", "opp", "raise", 3), h("turn", "opp", "raise", 8),
      h("river", "opp", "raise", 20)],
     "river", False, {("open", "flop"), ("open", "turn"),
                      ("open", "river")}),

    ("we check, they bet -> open (not rr)",
     [h("flop", "me", "check"), h("flop", "opp", "raise", 3)],
     "flop", False, {("open", "flop")}),

    ("call then raise: their raise after OUR raise on same street",
     [h("flop", "opp", "raise", 3), h("flop", "me", "call", 3),
      h("flop", "me", "raise", 9), h("flop", "opp", "raise", 27)],
     "flop", True, {("open", "flop"), ("rr", "flop")}),

    ("nothing happened",
     [], "flop", False, set()),
]

fails = 0
for name, hist, street, exp_rr, exp_raises in cases:
    got_rr = _facing_reraise(hist, street)
    got_raises = _opp_raises(hist)
    ok = (got_rr == exp_rr and got_raises == exp_raises)
    if not ok:
        fails += 1
        print(f"FAIL {name}: rr={got_rr} (exp {exp_rr}) "
              f"raises={got_raises} (exp {exp_raises})")
    else:
        print(f"ok   {name}")

# _opp_raised consistency: it counts OPPONENT raises only (the function
# is used to decide "are we facing their aggression")
for name, hist, street, _, _ in cases:
    raised = _opp_raised(hist, street)
    any_raise = any(e["street"] == street and e["action"] == "raise"
                    and e["actor"] == "opp" for e in hist)
    if raised != any_raise:
        fails += 1
        print(f"FAIL _opp_raised on '{name}': {raised} vs {any_raise}")

print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILURES'}")
sys.exit(1 if fails else 0)
