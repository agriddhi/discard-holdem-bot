"""Unit tests for batch R (watchdog) + D (per-street aggression)."""
import sys
import time
sys.path.insert(0, ".")
from bot import Bot

fails = 0


def check(name, cond, extra=""):
    global fails
    if cond:
        print(f"ok   {name}")
    else:
        fails += 1
        print(f"FAIL {name} {extra}")


# ---- street_fold_rate ---------------------------------------------------
b = Bot()
check("no data -> None", b.street_fold_rate("flop") is None)

b.st["faced"] = 12
b.st["folds"] = 6                      # global 0.50
check("street w/o data falls back to global",
      abs(b.street_fold_rate("flop") - 0.50) < 1e-9)

b.st["faced_s"]["turn"] = 10
b.st["folds_s"]["turn"] = 2            # street 0.20, w = 10/16
exp = 0.50 + (10 / 16) * (0.20 - 0.50)
check("street shrinks toward global",
      abs(b.street_fold_rate("turn") - exp) < 1e-9,
      f"got {b.street_fold_rate('turn')} exp {exp}")

b.st["faced_s"]["preflop"] = 20
b.st["folds_s"]["preflop"] = 15        # street 0.75
fr = b.street_fold_rate("preflop")
check("high preflop fold rate surfaces", fr > 0.6, f"got {fr}")

# ---- bluff_freq ---------------------------------------------------------
bf = b.bluff_freq("preflop")
check("bluff freq capped at 0.5", abs(bf - 0.5) < 1e-9, f"got {bf}")
bf_t = b.bluff_freq("turn")
check("turn bluff freq low", 0.03 <= bf_t < 0.10, f"got {bf_t}")
b2 = Bot()
check("no data -> default 0.15", abs(b2.bluff_freq("river") - 0.15) < 1e-9)

# ---- watchdog n_for -----------------------------------------------------
b3 = Bot()
b3.reply_t0 = time.perf_counter() - 3.0        # reply already 3s old
check("slow reply -> n=60", b3.n_for(600) == 60, f"got {b3.n_for(600)}")
b3.reply_t0 = time.perf_counter() - 1.5        # 1.5s elapsed
check("mildly slow reply -> n=150", b3.n_for(600) == 150)
b3.reply_t0 = None
b3.stall = 2
check("stall active -> n=60", b3.n_for(600) == 60)
check("stall decrements", b3.n_for(600) == 60 and b3.stall == 0)
check("stall exhausted -> normal n",
      b3.n_for(600) == 600, f"got {b3.n_for(600)}")

b3._note_speed(1000)                  # abnormally slow call
check("slow call sets stall", b3.stall == 4)
b3._note_speed(50)                    # normal call does not clear/set
check("fast call leaves stall alone", b3.stall == 4)

# ---- end_hand per-street counters ---------------------------------------
b4 = Bot()
b4.end_hand({
    "net": -3, "result": "fold",
    "history": [
        {"street": "flop", "actor": "me", "action": "raise", "amount": 3},
        {"street": "flop", "actor": "opp", "action": "fold"},
    ],
})
check("faced_s flop counted",
      b4.st["faced_s"].get("flop") == 1, str(b4.st["faced_s"]))
check("folds_s flop counted",
      b4.st["folds_s"].get("flop") == 1, str(b4.st["folds_s"]))
check("global faced/folds still work",
      b4.st["faced"] == 1 and b4.st["folds"] == 1)

b4.end_hand({
    "net": 2, "result": "fold",
    "history": [
        {"street": "turn", "actor": "me", "action": "raise", "amount": 8},
        {"street": "turn", "actor": "opp", "action": "call"},
        {"street": "river", "actor": "me", "action": "raise", "amount": 20},
        {"street": "river", "actor": "opp", "action": "fold"},
    ],
})
check("call counts faced but not folds",
      b4.st["faced_s"].get("turn") == 1 and "turn" not in b4.st["folds_s"],
      str(b4.st))
check("river fold counted separately",
      b4.st["folds_s"].get("river") == 1)
check("totals consistent (cumulative over both hands)",
      b4.st["faced"] == 3 and b4.st["folds"] == 2, str(b4.st))

# a response on a NEW street must not leak the previous street's state
b5 = Bot()
b5.end_hand({
    "net": 0, "result": "fold",
    "history": [
        {"street": "flop", "actor": "me", "action": "raise", "amount": 3},
        {"street": "turn", "actor": "opp", "action": "fold"},
    ],
})
check("street change resets facing state",
      b5.st["faced"] == 0, str(b5.st))

print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILURES'}")
sys.exit(1 if fails else 0)
