# Discard Hold'em — Tournament Bot

Entry for the Pokerbots "Discard Hold'em" competition.

**Submission artefact: `submission.zip`** — a single `bot.py` at the zip root
(Rulebook 5.10). Nothing else is submitted.

## Files

| File | What it is |
|---|---|
| `submission.zip` | **The submission.** Contains exactly one file: `bot.py`. |
| `bot.py` | The strategy source (inlines `equity.py` when built). |
| `equity.py` | Vectorised hand evaluator + Monte-Carlo equity. |
| `build_submission.py` | Merges `bot.py` + `equity.py` → `dist/bot.py`, zips it. |
| `engine.py` | Official local match runner (unmodified starter kit). |

## Running a match locally

```powershell
py -3.11 engine.py bot.py example_bots/random_bot.py
```

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

**Decisions.** Value thresholds with a call margin; bet size scales with
equity; bluffs are sized by how often the opponent folds to our
aggression; the raise/fold mix adapts to folder vs. station opponents.

**Opponent model.** Our equity against *their* betting range is not our
equity against a random hand. We estimate their range threshold `t` from
the percentiles of hands they show down after betting, then convert:
equity vs their range ≈ `(p - t)/(1 - t)`. Separate pools for open bets
vs re-raises and for the river vs earlier streets.

## Two failure modes found and fixed

**1. The fold spiral.** `t` was learned *only* from showdowns — but we
only reach a showdown if we call, and the prior (`t = 0.55`) makes us
fold. Against an opponent who raises on ~every opportunity we folded
100% of preflop hands and lost every blind (**−790 to −810 chips per
400-hand match**).

*Fix.* Estimate `t` from their **action frequency**, which needs no
showdowns: an opponent who acts on nearly every opportunity cannot have
a selective range. A deliberately coarse guard (≥0.90 take-rate over
≥25 opportunities, per street) only fires in the degenerate case and
leaves normal play untouched. Capped score vs jam/maniac opponents:
**−2000 (0/5 wins) → +2000 (5/5 wins)**.

**2. Time-bank exhaustion on a slower machine.** The old watchdog
shrank sample counts at fixed thresholds. On a machine 2× slower the bot
burned the whole 75 s bank and **forfeited the match**.

*Fix.* The bot measures the real cost of Monte-Carlo work on the machine
it runs on (fixed cost + per-sample slope) and sizes each decision to
the time left in the bank, with a hard per-reply ceiling and a
last-resort cheap reply. Verified to avoid forfeiting at 2×, 4×, 8×,
16× and 32× simulated CPU slowdown.

## Constraints (verified)

- Python 3.11, stdlib + NumPy only (SciPy allowed but unused).
- No file writes, no network, no subprocess (read-only FS safe).
- stdout carries only protocol JSON; diagnostics go to stderr.
- Peak RSS ~84 MB of the 1 GB limit; worst single equity call ~87 ms
  against a 5 s per-reply limit.

## Validation

- 13-seed Stage-1 ladder: **13/13 wins, capped 5200** (ceiling).
- 0 protocol notices, no STALLs, time use 5.8–15.6 s of a 60 s bank.
- All example-bot regression tests pass.
