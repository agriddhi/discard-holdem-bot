"""Unit tests for pot-weighted sampling (stake_n)."""
import sys
import time
sys.path.insert(0, ".")
from bot import Bot, FLOP_N, TURN_N  # noqa: E402

fails = 0


def check(name, cond, extra=""):
    global fails
    if cond:
        print(f"ok   {name}")
    else:
        fails += 1
        print(f"FAIL {name} {extra}")


b = Bot()
b.tl = 30000
b.total_hands = 200
b.hand_id = 1

# small pot: barely above base
n = b.stake_n(600, 4)
check("min pot ~1.08x", n == int(1.08 * 600), f"got {n}")
# mid pot
n = b.stake_n(600, 25)
check("pot 25 -> 1.5x", n == 900, f"got {n}")
# big pot: capped at 2x
n = b.stake_n(600, 50)
check("pot 50 -> 2x", n == 1200, f"got {n}")
n = b.stake_n(600, 500)
check("huge pot capped at 2x", n == 1200, f"got {n}")
# turn base
n = b.stake_n(TURN_N, 10)
check("turn base scales", n == int(1.2 * TURN_N), f"got {n}")

# time-bank shrink still applies on top of the scaled base
b.tl = 40000
b.total_hands = 200
b.hand_id = 150                      # 51 hands left -> per ~784ms: full
n = b.stake_n(600, 25)
check("healthy bank keeps scaled n", n == 900, f"got {n}")
b.tl = 3000
b.hand_id = 199                      # 2 hands left but tl small: per=1500 full
n = b.stake_n(600, 25)
check("bank still ok at end", n == 900, f"got {n}")
b.tl = 8000
b.hand_id = 100                      # 101 left, per ~79ms -> 0.75x branch
n = b.stake_n(600, 25)
check("shrunk bank scales base first", n == int(0.75 * 900), f"got {n}")

# stall watchdog dominates (returns fixed 60 regardless of scaling)
b.stall = 1
n = b.stake_n(600, 100)
check("stall -> 60 even in big pot", n == 60, f"got {n}")

# reply-elapsed watchdog also dominates
b.stall = 0
b.reply_t0 = time.perf_counter() - 3.0
n = b.stake_n(600, 100)
check("slow reply -> 60 even in big pot", n == 60, f"got {n}")
b.reply_t0 = time.perf_counter() - 2.0
n = b.stake_n(600, 100)
check("mildly slow reply -> 150", n == 150, f"got {n}")

# river path: action() must pass n=1 (exact) without scaling
b.reply_t0 = None
src = open("bot.py", encoding="utf-8").read()
check("river keeps exact n=1",
      "self.stake_n(base, pot) if base else 1" in src)

print(f"\n{'ALL PASS' if fails == 0 else str(fails) + ' FAILURES'}")
sys.exit(1 if fails else 0)
