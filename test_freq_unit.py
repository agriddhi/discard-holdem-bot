"""Unit tests for the frequency guard (no engine needed).

Checks the semantics that matter:
  * opp_t returns the unselective threshold when the take rate is high
  * it returns the prior / learned value otherwise
  * realized_eq then treats their range as random (r == p)
  * the open/re-raise split matches the threshold pools' semantics
  * per-hand state does not leak between hands

Usage: py -3.11 test_freq_unit.py
"""
import sys

sys.path.insert(0, ".")
import bot as B  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}{'' if cond else '  ' + detail}")
    if not cond:
        fails.append(name)


print("1) guard fires only at a high take rate")
b = B.Bot()
b.opp_opps[("open", "preflop")] = 40
b.opp_takes[("open", "preflop")] = 40          # 100%
check("rate 1.00 -> unselective",
      b.opp_t("preflop") == B.T_UNSELECTIVE, str(b.opp_t("preflop")))
b.opp_takes[("open", "preflop")] = 20          # 50%
check("rate 0.50 -> not unselective",
      b.opp_t("preflop") != B.T_UNSELECTIVE, str(b.opp_t("preflop")))
b.opp_takes[("open", "preflop")] = 36          # 90%
check("rate 0.90 -> unselective (threshold inclusive)",
      b.opp_t("preflop") == B.T_UNSELECTIVE, str(b.opp_t("preflop")))
b.opp_takes[("open", "preflop")] = 35          # 87.5%
check("rate 0.875 -> not unselective",
      b.opp_t("preflop") != B.T_UNSELECTIVE, str(b.opp_t("preflop")))

print("2) too few observations -> no verdict")
b2 = B.Bot()
b2.opp_opps[("open", "preflop")] = 5
b2.opp_takes[("open", "preflop")] = 5
check("5 opportunities -> no verdict",
      b2.opp_t("preflop") == B.T_OPEN_EARLY, str(b2.opp_t("preflop")))

print("3) guard overrides a learned value (anti-spiral)")
b3 = B.Bot()
b3.thr["open_e"] = [1, 0.999]      # one showdown of a monster hand
b3.opp_opps[("open", "preflop")] = 40
b3.opp_takes[("open", "preflop")] = 40
check("unselective beats learned value",
      b3.opp_t("preflop") == B.T_UNSELECTIVE, str(b3.opp_t("preflop")))

print("4) realized_eq treats an unselective range as random")
b4 = B.Bot()
b4.opp_opps[("open", "preflop")] = 40
b4.opp_takes[("open", "preflop")] = 40
for p in (0.3, 0.5, 0.7):
    r = b4.realized_eq(p, "preflop")
    check(f"realized_eq(p={p}) == p", abs(r - p) < 1e-9, f"got {r:.4f}")

print("5) normal opponent keeps the learned value")
b5 = B.Bot()
b5.thr["open_e"] = [20, 20 * 0.80]   # mean percentile 0.80
b5.opp_opps[("open", "preflop")] = 60
b5.opp_takes[("open", "preflop")] = 12          # rate 0.20
t = b5.opp_t("preflop")
expect_prior = B.T_OPEN_EARLY
check("low rate -> learned/prior path used",
      t != B.T_UNSELECTIVE and abs(t - expect_prior) < 0.4, f"got {t:.3f}")

print("6) open vs re-raise split matches the pools")
b6 = B.Bot()
b6._reset_aggression_state()
b6._count_aggression({"street": "flop"}, "me", "raise")
b6._count_aggression({"street": "flop"}, "opp", "raise")
check("their raise after ours -> rr pool",
      b6.opp_takes.get(("rr", "flop"), 0) == 1
      and b6.opp_takes.get(("open", "flop"), 0) == 0,
      f"rr={b6.opp_takes} ")

b7 = B.Bot()
b7._reset_aggression_state()
b7._count_aggression({"street": "flop"}, "opp", "raise")
check("their raise first -> open pool",
      b7.opp_takes.get(("open", "flop"), 0) == 1
      and b7.opp_takes.get(("rr", "flop"), 0) == 0,
      f"open={b7.opp_takes}")

print("7) per-hand state does not leak")
b8 = B.Bot()
b8._reset_aggression_state()
b8._count_aggression({"street": "preflop"}, "me", "raise")
b8._reset_aggression_state()
b8._count_aggression({"street": "preflop"}, "opp", "raise")
check("stale 'raise' from a previous hand not carried over",
      b8.opp_takes.get(("open", "preflop"), 0) == 1
      and b8.opp_takes.get(("rr", "preflop"), 0) == 0,
      f"open/rr={b8.opp_takes}")

print("8) per-street separation: one street wide, another selective")
b9 = B.Bot()
b9.opp_opps[("open", "preflop")] = 40
b9.opp_takes[("open", "preflop")] = 40
b9.opp_opps[("open", "turn")] = 40
b9.opp_takes[("open", "turn")] = 4
check("preflop unselective, turn selective",
      b9.opp_t("preflop") == B.T_UNSELECTIVE
      and b9.opp_t("turn") != B.T_UNSELECTIVE,
      f"pf={b9.opp_t('preflop'):.2f} turn={b9.opp_t('turn'):.2f}")

print("\nPASS" if not fails else f"\nFAIL: {fails}")
sys.exit(1 if fails else 0)
