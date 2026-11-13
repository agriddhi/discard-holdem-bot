# Discard Hold'em — Tournament Bot

Entry point for the Pokerbots "Discard Hold'em" competition. The submitted
artifact is **`submission.zip`**: a single `bot.py` at the zip root (Rulebook 5.10).

## Layout

| File | What it is |
|---|---|
| `bot.py` | The strategy. Single file, stdlib + NumPy only. |
| `equity.py` | Vectorised hand evaluator + Monte-Carlo equity (inlined into the submission). |
| `engine.py` | Official local match runner (unmodified). |
| `build_submission.py` | Merges `bot.py` + `equity.py` → `dist/bot.py`. |
| `final_check.ps1` | Full pre-submission validation (build → zip → e2e from the zip). |
| `ladder.py` | 13-seed Stage-1 ladder; reports raw and **capped** score. |
| `audit_submission.py` | Checks the shipped zip against the runtime constraints. |
| `slow_test.py` | Emulates a slower CPU to prove we never forfeit on time. |
| `test_freq_unit.py`, `test_guard_behavior.py` | Tests for the opponent-range model. |
| `example_bots/` | Local opponents: the three shipped examples plus harder ones. |

## The game in one paragraph

Heads-up, 3 cards each, blinds 1/2, 200 starting stack. The flop betting
round is played with **three** cards each; afterwards both players
**discard one card**, face up, and play turn and river with two cards
each. Every match is played twice with the seats swapped (duplicate
deals). Stage 1 is a 6-round Swiss qualifier (~400 hands/round); Stage 2
is a 32-team round-robin (~500 duplicate deals each).

## Strategy

**Equity.** `equity.py` evaluates 7-card hands with NumPy and estimates
equity by Monte-Carlo. Two forms are used: `equity3` (3-card hand, one
keep per pair — used preflop and on the flop) and `equity2` (2-card
hand, known board, the two exposed discards removed from the deck).

**Decisions.** Value thresholds (`BET_VALUE`, `RAISE_VALUE`) with
`CALL_MARGIN`; bet size scales with equity; bluffs are sized by how
often the opponent folds to our aggression; the raise/fold mix adapts to
whether we are up against a folder or a station.

**Opponent model.** The key idea is that our equity against *their*
betting range is not our equity against a random hand. We estimate their
range threshold `t` from the percentiles of the hands they show down
after betting, then convert: equity vs their range ≈ `(p - t)/(1 - t)`.
Separate pools for open bets vs re-raises and for the river vs earlier
streets, because those ranges differ a lot.

## Two failure modes found and fixed

**1. The fold spiral.** `t` was learned *only* from showdowns — but we
only reach a showdown if we call, and the prior (`t = 0.55`, a strong
range) makes us fold. So against an opponent who raises on ~every
opportunity we folded 100% of preflop hands and lost every blind:
**−790 to −810 chips per 400-hand match**.

*Fix.* Estimate `t` from their **action frequency**, which needs no
showdowns. An opponent who takes an action on nearly every opportunity
cannot have a selective range, so their range is wide. Implemented as a
deliberately coarse guard (≥0.90 take-rate over ≥25 opportunities, per
street): a continuous frequency→`t` fit was measurably miscalibrated for
ordinary opponents, whereas the coarse guard only fires in the degenerate
case and leaves normal play untouched.

Measured over 5 seeds per opponent (capped score, i.e. what the
tournament sees):

| Opponent | Before | After |
|---|---|---|
| jam (raises every hand) | −2000 (0/5 won) | **+2000 (5/5 won)** |
| maniac (raises constantly) | −2000 (0/5 won) | **+2000 (5/5 won)** |
| tough_bot | +1200 (4/5) | **+2000 (5/5)** |
| value_bot | +1896 (5/5) | +2000 (5/5) |
| aggro / caller / folder | +2000 | +2000 |

**2. Time-bank exhaustion on a slower machine.** The old watchdog
shrunk sample counts at fixed thresholds. On a machine 2× slower than
ours, the bot used the whole 75 s bank and **forfeited the match** — the
worst possible outcome, since a forfeit also forfeits the match points.

*Fix.* Measure the actual cost of Monte-Carlo work on the machine we
are running on (fixed cost + per-sample slope) and size each decision to
the time actually left in the bank, with a hard ceiling on a single
reply (the engine kills a bot at 5 s per reply). When even the minimum
work does not fit, answer with the engine's default instead of timing
out.

Stress-tested by injecting a delay into every equity call:

| Simulated CPU | Before | After |
|---|---|---|
| 2× slower | **forfeit** | no forfeit (130 s of 150 s) |
| 4× slower | — | no forfeit (139 s) |
| 8× slower | forfeit | no forfeit (148 s) |
| 16× slower | forfeit | no forfeit (149 s) |
| 32× slower | forfeit | no forfeit, but weak play (loses instead of forfeiting) |

## Constraints

Verified by `audit_submission.py` against the shipped zip:

- Python 3.11, stdlib + NumPy only (SciPy allowed but unused).
- No file writes (read-only filesystem), no network, no subprocess.
- stdout carries only protocol JSON; all diagnostics go to stderr.
- Peak RSS 84 MB of the 1 GB limit; worst single equity call 87 ms
  against a 5 s per-reply limit.

## Reproducing

```powershell
py -3.11 build_submission.py          # -> dist/bot.py
py -3.11 ladder.py bot.py logs_check  # 13-seed Stage-1 ladder
py -3.11 audit_submission.py submission.zip
powershell -ExecutionPolicy Bypass -File final_check.ps1
```

Note: the bot uses unseeded RNG, so a single match varies by ±500 chips.
Compare **capped scores and win counts over many seeds**, never a
single match.
