"""
Discard Hold'em bot - equity strategy + within-leg opponent model.

Phases:
  1  protocol safety: 3 layers (logic -> validate_reply -> rescue loop)
  2  equity brain:     equity.py (validated vs official engine, 0 mismatches)
  3  betting:          pot odds + value/bluff thresholds, legal raise sizing
  4  opponent model:   fold-to-aggression, aggression rate, bluff/showdown
                       habits, discard habits - all tracked within one leg

stdout carries ONLY flushed protocol JSON. Everything else -> stderr.
"""

import sys
import json
import traceback
import random
import time

import numpy as np

import equity as EQ

RANKS = "23456789TJQKA"
SUITS = "shdc"

# ---- strategy parameters -------------------------------------------------
PREFLOP_N = 400        # MC samples preflop
FLOP_N = 600           # MC samples on the flop (also drives the discard)
TURN_N = 800           # MC samples on the turn
# river: exact enumeration (no sampling)

BET_VALUE = 0.62       # bet/raise for value at/above this equity
RAISE_VALUE = 0.72     # raise instead of flat-calling at/above this equity
CALL_MARGIN = 0.03     # edge over pot odds required to call
# Facing a bet, our equity-vs-random overstates equity-vs-their-range: a
# voluntary bet comes from hands with percentile >= t on this board, so our
# equity against that range is (p - t)/(1 - t).  t is learned per leg from
# their shown-down bets (see opp_t).  Priors fitted offline from 14 full
# matches with fit_t.py -- most importantly a RE-RAISE over us comes from a
# far stronger range (top ~18%) than an open bet (top ~40%).
T_OPEN_EARLY = 0.55   # open bets / barrels on flop & turn   (fit 0.554)
T_OPEN_RIVER = 0.61   # open bets on the river               (fit 0.611)
T_RR_EARLY = 0.80     # re-raised over us, preflop..turn     (fit 0.801)
T_RR_RIVER = 0.835    # re-raised over us on the river       (fit 0.835)
THR_K = 6.0           # prior weight when shrinking the observed threshold
FREQ_MIN_OPPS = 25    # opponent opportunities needed before their action
                       # frequency says anything about their range
FREQ_UNSELECTIVE = 0.90   # take-rate above which their range cannot be
                       # selective (they act on nearly every chance)
T_UNSELECTIVE = -0.60  # threshold for an unselective range: below the
                       # -0.45 cut-off, so equity vs their range is
                       # treated as equity vs a random holding
CAL_GAP_PRIOR = 0.20   # assumed p - realized gap before we have called enough
MIN_N = 12            # fewest Monte-Carlo samples we will ever use: a
                       # noisy decision beats an exhausted time bank
REPLY_BUDGET_MS = 900  # target ceiling for ONE equity call: the engine
                       # kills a bot that takes 5 s to reply, and that
                       # forfeits the whole match, so stay well inside
PREFLOP_WIDEN = 0.18  # a heavy preflop folder lowers our open threshold
                       # (they fold 77% to our opens: top-16% opens get
                       #  widened toward top-24% vs a measured folder)
PREFLOP_OPEN = 6       # first preflop raise-to (3bb)
OPEN_FRAC = 0.6        # value bet size as fraction of pot (bluffs use this too)
BLUFF_FRAC = 0.5       # bluff size as fraction of pot
# value bets scale with equity: thin value -> small bet (they call a wide
# range anyway), thick value -> big bet (extract from their wide calls).
VBET_BASE = 0.45       # pot-fraction at VBET_REF equity
VBET_REF = 0.60        # reference equity
VBET_SLOPE = 2.0       # extra pot-fraction per unit of equity
VBET_MAX = 1.10        # cap: allow a modest overbet with the nuts
RAISE_OVER_FRAC = 0.6  # value raise over a bet: frac of (pot + to_call)
CLOSE_BAND = 0.015     # discard tie-break band (MC noise)

ERR_LIMIT = 8          # max traceback lines logged per leg (64KB stderr cap)
err_count = 0


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def log_err(msg):
    global err_count
    if err_count < ERR_LIMIT:
        err_count += 1
        log(msg)


# ------------------------------------------------------- safe reply builders
def safe_action(req):
    """A reply guaranteed legal for this request (no raise: needs amount)."""
    legal = req.get("legal_actions") or []
    if "check" in legal:
        return {"type": "action", "action": "check"}
    if "call" in legal:
        return {"type": "action", "action": "call"}
    if "fold" in legal:
        return {"type": "action", "action": "fold"}
    if "raise" in legal:
        lo = req.get("min_raise", 2)
        hi = req.get("max_raise", lo)
        if hi < lo:
            hi = lo
        return {"type": "action", "action": "raise", "amount": int(lo)}
    return {"type": "action", "action": "check"}


def safe_discard(req):
    """Lowest-ranked hole card (matches the engine's own default discard)."""
    cards = req.get("hole_cards") or []
    if not cards:
        return {"type": "discard", "card": "2s"}
    worst = min(cards, key=lambda c: (RANKS.index(c[0]), SUITS.index(c[1])))
    return {"type": "discard", "card": worst}


def validate_reply(reply, req_type, req=None):
    """Last line of defence: never send an illegal reply."""
    try:
        if req_type == "action":
            legal = req.get("legal_actions") or []
            action = reply.get("action")
            if action not in legal:
                return safe_action(req)
            if action == "raise":
                amount = reply.get("amount")
                if isinstance(amount, bool) or not isinstance(amount, int):
                    return safe_action(req)
                lo, hi = req.get("min_raise", 0), req.get("max_raise", 0)
                if hi < lo:
                    hi = lo
                if not lo <= amount <= hi:
                    amount = int(max(lo, min(hi, amount)))
                return {"type": "action", "action": "raise", "amount": amount}
            return {"type": "action", "action": action}
        if req_type == "discard":
            card = reply.get("card")
            cards = req.get("hole_cards") or []
            if card not in cards:
                return safe_discard(req)
            return {"type": "discard", "card": card}
    except Exception:
        return None
    return None


# ------------------------------------------------------------- helpers
def _hist_raise_amount(history, street):
    """The opponent's most recent raise-to amount on `street`, or 0."""
    amt = 0
    for h in history:
        if (h.get("street") == street and h.get("actor") == "opp"
                and h.get("action") == "raise"):
            amt = h.get("amount") or 0
    return amt


def _opp_raised(history, street):
    return _hist_raise_amount(history, street) > 0


def _opp_raises(history):
    """{(kind, street)} for every opponent raise: 'open' or 'rr'.

    'rr' = their raise came immediately after our raise on the same
    street (a re-raise / 3-bet+), 'open' = an open bet or a barrel
    with no raise of ours in front.  Matches the tagging used to fit
    the priors in fit_t.py.
    """
    out = set()
    my_last = {}
    for h in history:
        st = h.get("street")
        if h.get("actor") == "me":
            my_last[st] = h.get("action")
        elif h.get("action") == "raise":
            kind = "rr" if my_last.get(st) == "raise" else "open"
            out.add((kind, st))
    return out


def _facing_reraise(history, street):
    """Is the bet we are facing this street a re-raise over us?"""
    prev = None
    for h in history:
        if h.get("street") != street:
            prev = None          # never carry an action across streets
            continue
        if h.get("actor") == "opp" and h.get("action") == "raise" \
                and prev == "raise":
            return True
        if h.get("actor") == "me":
            prev = h.get("action")
        else:
            prev = None
    return False


def _opp_checked_last(history, street):
    """Was the opponent's most recent action on `street` a check?"""
    for h in reversed(history):
        if h.get("street") == street:
            return h.get("actor") == "opp" and h.get("action") == "check"
    return False


def _hand_cat(cards):
    """0=high card .. 8=straight flush, official evaluator."""
    r = np.array([[RANKS.index(c[0]) for c in cards]])
    s = np.array([[SUITS.index(c[1]) for c in cards]])
    return int(EQ.eval7(r, s)[0]) // (16 ** 5)


class Bot:
    def __init__(self):
        self.total_hands = 200
        self.time_bank = 30000
        self.tl = 30000
        self.hand_id = 0
        self.hole = []
        self.my_discard = None
        self.opp_discard = None
        self.cache = {}
        # leg-long opponent model
        self.st = {
            "hands": 0, "net": 0,
            "faced": 0, "folds": 0,          # opp decisions facing our aggression
            "faced_s": {}, "folds_s": {},     # same, split by street
            "opp_raises": 0, "my_raises": 0,  # voluntary aggression counts
            "bet_showdowns": 0, "weak_showdowns": 0,  # opp bets that reached SD
            "dis_n": 0, "low_dis": 0,         # opp discard = lowest of their 3?
        }
        # equity-vs-random calibration: what we assumed when calling their
        # aggression vs how often we actually won at showdown.
        self.cal_n = 0
        self.cal_eq_sum = 0.0
        self.cal_win_sum = 0.0
        self.call_eq = None     # eq assumed at our last call facing a bet
        # Adaptive time budget.  The grader may be slower than the
        # development machine, and an exhausted time bank FORFEITS the
        # whole match, so the work we do per decision must scale with
        # the time actually left and the measured cost of an equity
        # call here.
        self.ms_per_sample = 0.0   # measured cost of one MC sample
        self.eq_fixed_ms = 0.0     # measured fixed cost of a call, ms
        self.eq_cost = 0.0         # EWMA of a whole equity call, ms
        # opponent betting-range thresholds: sum of their shown percentile
        # over showdowns, per behavior x street group.  Keys:
        # open_r/open_e = they bet with no raise of ours in front,
        # rr_r/rr_e     = they raised immediately after our raise.
        self.thr = {"open_r": [0, 0.0], "open_e": [0, 0.0],
                    "rr_r": [0, 0.0], "rr_e": [0, 0.0]}
        # How often they take each aggressive action, and how many chances
        # they had to take it.  This needs NO showdowns, which matters:
        # the showdown-based threshold pools below are fed by hands that
        # reached a showdown, and if we always fold to an opponent we
        # never see their cards -- so we never learn that their range is
        # wide, so we keep folding.  Measured: an opponent who raises
        # on ~every opportunity (a jamming opponent) beat us 800 chips
        # per 400-hand match purely because of that loop.
        #
        # Per street, because a range can be unselective on one street
        # and selective on another.
        self.opp_takes = {}       # (kind, street) -> times they raised
        self.opp_opps = {}        # (kind, street) -> their action slots
        # our last action per street (to split their raises into open
        # vs re-raise, exactly like the threshold pools do)
        self._my_last_act = {}
        self.eq_ms = 0.0
        self.eq_calls = 0
        # reliability watchdog: a stalled/suspended process must still
        # answer inside the 5 s per-reply limit (one environmental stall
        # forfeited a whole match in testing), so equity work shrinks when
        # this reply is already slow or a previous call stalled badly.
        self.reply_t0 = None
        self.stall = 0

    # ------------------------------------------------------------ observe
    def observe(self, msg):
        t = msg.get("type")
        if t == "init":
            self.total_hands = int(msg.get("total_hands") or 200)
            self.time_bank = int(msg.get("time_bank_ms") or 30000)
            self.tl = self.time_bank
            log(f"init hands={self.total_hands} bank={self.time_bank}ms")
        elif t == "new_hand":
            self.hand_id = int(msg.get("hand_id") or 0)
            self.hole = list(msg.get("hole_cards") or [])
            self.my_discard = None
            self.opp_discard = None
            self.call_eq = None
        elif t == "discard_result":
            self.my_discard = msg.get("my_discard")
            self.opp_discard = msg.get("opp_discard")
            hc = msg.get("hole_cards")
            if hc:
                self.hole = list(hc)
        elif t == "hand_result":
            self.end_hand(msg)
        elif t == "notice":
            log(f"NOTICE code={msg.get('code')} applied={msg.get('applied')}")
        # unknown types: ignored (forward compatibility)

    # ------------------------------------------------------- opponent model
    def _count_aggression(self, h, actor, act):
        """Count their aggressive actions and their chances to make one.

        Same open/re-raise split the threshold pools use: a raise right
        after our raise is a re-raise, otherwise it is an open.  Counting
        needs no showdowns, so it keeps working in the (bad) case where
        we never see their cards.
        """
        street = h.get("street")
        if actor == "me":
            self._my_last_act[street] = act
            return
        kind = "rr" if self._my_last_act.get(street) == "raise" else "open"
        key = (kind, street)
        self.opp_opps[key] = self.opp_opps.get(key, 0) + 1
        if act == "raise":
            self.opp_takes[key] = self.opp_takes.get(key, 0) + 1

    def _reset_aggression_state(self):
        """Per-hand state for the open/re-raise split."""
        self._my_last_act = {}

    def end_hand(self, msg):
        s = self.st
        s["hands"] += 1
        net = int(msg.get("net") or 0)
        s["net"] += net
        hist = msg.get("history") or []

        # walk the history: when did the opponent face our aggression?
        self._reset_aggression_state()
        cur_street = None
        opp_facing_me = False
        for h in hist:
            if h.get("street") != cur_street:
                cur_street = h.get("street")
                opp_facing_me = False
            actor, act = h.get("actor"), h.get("action")
            self._count_aggression(h, actor, act)
            if actor == "me":
                if act == "raise":
                    opp_facing_me = True
                    s["my_raises"] += 1
                else:
                    opp_facing_me = False
            else:
                if act == "fold":
                    if opp_facing_me:
                        s["faced"] += 1
                        s["folds"] += 1
                        s["faced_s"][cur_street] = \
                            s["faced_s"].get(cur_street, 0) + 1
                        s["folds_s"][cur_street] = \
                            s["folds_s"].get(cur_street, 0) + 1
                    opp_facing_me = False
                elif act == "call":
                    if opp_facing_me:
                        s["faced"] += 1
                        s["faced_s"][cur_street] = \
                            s["faced_s"].get(cur_street, 0) + 1
                    opp_facing_me = False
                elif act == "raise":
                    if opp_facing_me:
                        s["faced"] += 1
                        s["faced_s"][cur_street] = \
                            s["faced_s"].get(cur_street, 0) + 1
                    s["opp_raises"] += 1
                    opp_facing_me = False
                else:  # check
                    opp_facing_me = False

        # showdown analysis: did their voluntary aggression show up with a dud?
        opp_cards = msg.get("opp_hole_cards")
        board = msg.get("board") or []
        opp_discard = msg.get("opp_discard")
        if msg.get("result") == "showdown" and opp_cards and len(board) == 5:
            if _opp_raised(hist, "flop") or _opp_raised(hist, "turn") \
                    or _opp_raised(hist, "river"):
                s["bet_showdowns"] += 1
                if _hand_cat(list(opp_cards) + list(board)) == 0:
                    s["weak_showdowns"] += 1
            # discard habit: was their exposed discard the lowest of their 3?
            if opp_discard and len(opp_cards) == 2:
                three = list(opp_cards) + [opp_discard]
                lowest = min(three, key=lambda c: RANKS.index(c[0]))
                s["dis_n"] += 1
                if opp_discard == lowest:
                    s["low_dis"] += 1
            # percentile of their shown hand vs a random holding -- the same
            # scale as our own equity -- to learn the threshold t of each
            # part of their range (t = 2*mean(percentile) - 1).
            if len(opp_cards) == 2:
                try:
                    p_opp = self.equity2(list(opp_cards), list(board),
                                         self._extra_out(self.hole, board), 1)
                    flags = {"open_r": 0, "open_e": 0, "rr_r": 0, "rr_e": 0}
                    for kind, st in _opp_raises(hist):
                        k = kind + ("_r" if st == "river" else "_e")
                        if k in flags:
                            self.thr[k][0] += 1
                            self.thr[k][1] += p_opp
                            flags[k] = 1
                    log("POPP p=%.3f %s hid=%d"
                        % (p_opp, " ".join(f"{k}={v}"
                                           for k, v in flags.items()),
                           self.hand_id))
                except Exception:
                    pass

        # settle the equity calibration: what we assumed when calling their
        # aggression vs what actually happened at showdown.
        if self.call_eq is not None:
            if msg.get("result") == "showdown":
                self.cal_n += 1
                res = 1.0 if net > 0 else 0.5 if net == 0 else 0.0
                self.cal_eq_sum += self.call_eq[0]
                self.cal_win_sum += res
                log(f"CAL eq={self.call_eq[0]:.3f} res={res:.1f} "
                    f"street={self.call_eq[1]} odds={self.call_eq[2]:.3f} "
                    f"rr={int(self.call_eq[3])} "
                    f"net={net} "
                    f"hid={self.hand_id} hole={','.join(self.hole)} "
                    f"board={','.join(board)} "
                    f"out={','.join(self._extra_out(self.hole, board))}")
            self.call_eq = None

        if s["hands"] % 50 == 0:
            gap = (self.cal_eq_sum - self.cal_win_sum) / self.cal_n \
                if self.cal_n else 0.0

            def _fr(st):
                v = self.street_fold_rate(st, need=4)
                return f"{v:.2f}" if v is not None else "-"

            log(f"H{s['hands']} net={s['net']} faced={s['faced']} "
                f"folds={s['folds']} oppR={s['opp_raises']} myR={s['my_raises']} "
                f"cal={self.cal_n} gap={gap:+.3f} "
                f"fr={_fr('preflop')}/{_fr('flop')}/{_fr('turn')}"
                f"/{_fr('river')} "
                f"tO={self.opp_t('flop'):.2f}/{self.opp_t('river'):.2f}"
                f"({self.thr['open_e'][0]}/{self.thr['open_r'][0]}) "
                f"tRR={self.opp_t('flop', True):.2f}"
                f"/{self.opp_t('river', True):.2f}"
                f"({self.thr['rr_e'][0]}/{self.thr['rr_r'][0]})")

    def fold_rate(self):
        s = self.st
        if s["faced"] < 12:
            return None
        return s["folds"] / s["faced"]

    def street_fold_rate(self, street, need=6):
        """Their fold rate facing OUR aggression on `street`.

        They fold very differently by street (measured vs value_bot:
        preflop 77%, flop 48%, turn 17%, river 24%), but per-street
        samples are small, so shrink toward the global rate.
        """
        sr = None
        nf = self.st["folds_s"].get(street, 0)
        ns = self.st["faced_s"].get(street, 0)
        if ns >= need:
            sr = nf / ns
        fr = self.fold_rate()
        if sr is None:
            return fr
        if fr is None:
            return sr
        w = ns / (ns + 6.0)
        return fr + w * (sr - fr)

    def bet_value_adj(self):
        """Threshold shift: bet thinner vs folders, tighter vs calling stations."""
        fr = self.fold_rate()
        if fr is None:
            return 0.0
        if fr >= 0.5:
            return -0.04
        if fr <= 0.2:
            return 0.05
        return 0.0

    def bluff_freq(self, street="flop"):
        """Bluff frequency for a bet we open, by street.

        Bluff where they actually fold; go near-quiet where they call
        almost everything (turn/river vs value_bot).
        """
        fr = self.street_fold_rate(street)
        if fr is None:
            return 0.15
        return max(0.03, min(0.5, 0.15 + 1.2 * (fr - 0.4)))

    def call_margin_adj(self):
        """Call lighter vs light show-downs, tighter vs strong ones."""
        s = self.st
        if s["bet_showdowns"] >= 8:
            wr = s["weak_showdowns"] / s["bet_showdowns"]
            if wr > 0.35:
                return -0.04
            if wr < 0.15:
                return 0.04
        return 0.0

    def opp_t(self, street, reraise=False):
        """Threshold t of the range that does this action on `street`.

        They only bet hands whose percentile on this board is >= t.  If
        their betting range were [t, 1] its mean percentile would be
        (1 + t)/2, so from the percentile of their shown-down bets:

            t_hat = 2 * mean(percentile) - 1

        shrunk toward a prior until enough showdowns are observed (state
        resets each leg: the engine starts a fresh process per leg).
        Re-raises use their own pools: a raise over us comes from a far
        stronger range than an open bet (fit_t.py: 0.80+ vs 0.55-0.61).

        Their ACTION FREQUENCY is a second, independent estimate of the
        same quantity, and it needs no showdowns -- which matters,
        because the showdown estimate is unavailable exactly when it is
        needed most: if we always fold to them we never see their
        cards, so we never learn that their range is wide, so we keep
        folding.  When the frequency is decisive it overrides the
        learned value (see freq_t).
        """
        if reraise:
            key = "rr_r" if street == "river" else "rr_e"
            prior = T_RR_RIVER if street == "river" else T_RR_EARLY
            kind = "rr"
        else:
            key = "open_r" if street == "river" else "open_e"
            prior = T_OPEN_RIVER if street == "river" else T_OPEN_EARLY
            kind = "open"
        n, sm = self.thr[key]
        # The frequency signal, when it is decisive, overrides the learned
        # value: an opponent who takes this action on nearly every
        # opportunity has an unselective range, and that is true no
        # matter what the few showdowns we happened to see suggest.
        # (A single showdown of theirs would otherwise pull the prior
        # back up and restart the fold spiral.)
        freq_t = self.freq_t(kind, street)
        if freq_t is not None:
            return freq_t
        if n <= 0:
            return prior
        t_hat = 2.0 * (sm / n) - 1.0
        w = n / (n + THR_K)
        return max(-0.30, min(0.95, prior + w * (t_hat - prior)))

    def freq_t(self, kind, street):
        """Detect an UNSELECTIVE range from their action frequency.

        The threshold pools are fed by showdowns, which we never see if
        we fold every hand -- and folding every hand is what the prior
        (a strong range) makes us do.  That is a trap: an opponent who
        takes this action on nearly every opportunity cannot be
        selecting, so their range is wide and our equity against it is
        close to our equity against a random hand.

        So: if they take the action on almost every chance they get,
        report an unselective range.  This is deliberately a coarse
        guard rather than a continuous estimate -- a continuous fit was
        measurably miscalibrated for ordinary opponents, whereas this
        only fires in the degenerate case and leaves normal play
        untouched.
        """
        key = (kind, street)
        opps = self.opp_opps.get(key, 0)
        if opps < FREQ_MIN_OPPS:
            return None
        if self.opp_takes.get(key, 0) / opps >= FREQ_UNSELECTIVE:
            return T_UNSELECTIVE
        return None

    def cal_gap(self):
        """Mean (assumed - realized) equity over our calls facing a bet.

        Measured from our own showdowns, so it tracks the part the
        percentile model misses: draws that got there, big bets from the
        top of their range, and boards where strength is not a total
        order.  Falls back to a prior until enough calls are seen.
        """
        if self.cal_n >= 10:
            gap = (self.cal_eq_sum - self.cal_win_sum) / self.cal_n
            return max(0.0, min(0.45, gap))
        return CAL_GAP_PRIOR

    def realized_eq(self, p, street, reraise=False):
        """Our equity against the range that actually bets on `street`.

        On a fixed board hand strength is nearly a total order, so p --
        equity vs a random holding -- doubles as the hand's percentile.
        If they only bet percentile >= t, a hand at percentile p wins
        (p - t) / (1 - t) of the time against that range.  On the river
        we additionally cap the result with the gap measured from our
        own calls, which keeps the model honest where it is optimistic.
        """
        if p >= 0.999:            # the nuts: no range can beat us
            return 1.0
        t = self.opp_t(street, reraise)
        if t <= -0.45:            # they bet anything: their range is random
            r = p
        else:
            r = (p - t) / (1.0 - t)
        if street == "river":
            r = min(r, p - self.cal_gap())
        return max(0.0, min(1.0, r))

    def desperate(self):
        """True when we cannot afford even the minimum equity work.

        On a machine far slower than expected, the sample floor alone
        can exceed the whole leg's time bank.  Then any equity call is
        a forfeit, so we must reply with a cheap, sane decision instead
        (the engine's own default), keeping the match alive.
        """
        tl = self.tl
        if tl is None or self.ms_per_sample <= 0:
            return False
        hands_left = max(1, self.total_hands - self.hand_id + 1)
        budget_ms = tl * 0.85 / hands_left
        per_call = budget_ms / self.calls_per_hand()
        cheapest = self.eq_fixed_ms + MIN_N * self.ms_per_sample
        return cheapest > per_call

    # ------------------------------------------------------------- equity
    def n_for(self, base):
        """Sample count to use, sized to the time we actually have.

        The hard limits are: 5 s per reply, and a cumulative time bank
        for the whole leg.  Breaching either forfeits the match, so the
        amount of Monte-Carlo work per decision has to adapt to the
        machine we are actually running on: a slower box needs fewer
        samples, and a fast box can afford more.

        We measure the cost of an equity call (ms per sample) as we go,
        then ask: how many samples fit in the time budget left for the
        remaining hands?  That keeps the whole leg inside the bank
        regardless of how fast the grader is.

        Hard floors keep us answering at all: a decision with very few
        samples is noisy but far better than a forfeit.
        """
        if self.stall > 0:            # recent equity call stalled badly
            self.stall -= 1
            return 60
        if self.reply_t0 is not None:  # this reply is already slow
            el = (time.perf_counter() - self.reply_t0) * 1000.0
            if el > 2500:
                return 60
            if el > 1200:
                return 150

        tl = self.tl
        if tl is None:
            return base
        # Leave a margin: the engine also charges us for its own I/O and
        # we want slack for the tail of the leg.
        hands_left = max(1, self.total_hands - self.hand_id + 1)
        budget_ms = tl * 0.85 / hands_left
        # How many equity calls one hand costs us: measured, not guessed.
        # A hand makes a preflop, a flop, a discard and a turn call, so
        # roughly 3-4 calls; counting the real average keeps the budget
        # honest on any machine.
        calls_per_hand = self.calls_per_hand()
        per_call = budget_ms / calls_per_hand
        # ALSO bound a single reply: the engine kills us at 5 s per
        # reply no matter how much bank is left, and a single slow call
        # forfeits the whole match.  So cap the work so that one call
        # stays comfortably inside that limit.
        per_call = min(per_call, REPLY_BUDGET_MS)
        if self.ms_per_sample > 0:
            # cost(n) ~= fixed + slope*n  ->  n <= (budget - fixed)/slope
            fixed = min(self.eq_fixed_ms, per_call * 0.5)
            afford = int((per_call - fixed) / self.ms_per_sample)
            if afford < base:
                base = max(MIN_N, afford)
        if tl < 1200:
            base = min(base, 80)
        return max(MIN_N, int(base))

    def calls_per_hand(self):
        """Measured equity calls per hand (a hand makes several)."""
        hands = self.st.get("hands") or 0
        if hands < 3 or self.eq_calls < 4:
            return 3.0            # sensible default before we know
        cph = self.eq_calls / float(hands)
        return max(1.0, min(6.0, cph))

    def _note_cost(self, dur_ms, n):
        """Record how expensive this machine's Monte-Carlo work is.

        An equity call has a fixed part (numpy setup, ~1 ms) and a
        per-sample part (the part that scales with the sample count we
        choose).  Only calls with enough samples give a clean estimate
        of the per-sample slope -- at n=12 the fixed part dominates and
        the naive dur/n overstates the slope by two orders of
        magnitude, which would make us shrink samples for no reason.
        """
        if n >= 64:
            per = dur_ms / n
            self.ms_per_sample = per if self.ms_per_sample <= 0 \
                else 0.7 * self.ms_per_sample + 0.3 * per
            # fixed part: total minus the per-sample part
            fixed = max(0.0, dur_ms - per * n)
            self.eq_fixed_ms = fixed if self.eq_fixed_ms <= 0 \
                else 0.7 * self.eq_fixed_ms + 0.3 * fixed
        self.eq_cost = dur_ms if self.eq_cost <= 0 \
            else 0.8 * self.eq_cost + 0.2 * dur_ms

    def _note_speed(self, ms):
        """Watchdog: an abnormally slow equity call shrinks the next few."""
        if ms > 800:
            self.stall = 4
            log(f"STALL eq_ms={ms:.0f} hid={self.hand_id}")

    def stake_n(self, base, pot):
        """Bigger pots get more MC samples: precision is worth more there.

        Small pots ~1.1x, big pots 2x the base, so this reallocates
        samples from low-stakes to high-stakes decisions at roughly the
        average cost of a flat increase.
        """
        return self.n_for(int(min(2.0, 1.0 + pot / 50.0) * base))

    def _cache_put(self, key, val):
        if len(self.cache) > 600:
            self.cache.clear()
        self.cache[key] = val

    def equity3(self, hole, board, n):
        """Per-keep equities for a 3-card hand (flop & preflop). -> np(3,)"""
        key = (tuple(hole), tuple(board), "3")
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        t0 = time.perf_counter()
        eqs, _ = EQ.equity_mc([EQ.cid(c) for c in hole],
                              [EQ.cid(c) for c in board],
                              3, n=n, per_keep=True)
        dur = (time.perf_counter() - t0) * 1000
        self.eq_ms += dur
        self._note_speed(dur)
        self._note_cost(dur, n)
        self.eq_calls += 1
        self._cache_put(key, eqs)
        return eqs

    def equity2(self, hole, board, extra, n):
        """Equity of a 2-card hand on a known board. -> float"""
        key = (tuple(hole), tuple(board), tuple(sorted(extra)), "2")
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        t0 = time.perf_counter()
        eq = EQ.equity_mc([EQ.cid(c) for c in hole],
                          [EQ.cid(c) for c in board],
                          2, n=n, per_keep=False,
                          known_extra=[EQ.cid(c) for c in extra])
        dur = (time.perf_counter() - t0) * 1000
        self.eq_ms += dur
        self._note_speed(dur)
        self._note_cost(dur, n)
        self.eq_calls += 1
        self._cache_put(key, eq)
        return eq

    def _extra_out(self, hole, board):
        """Cards out of play: both exposed discards (never in hole/board)."""
        out = []
        for c in (self.my_discard, self.opp_discard):
            if c and c not in hole and c not in board:
                out.append(c)
        return out

    # ------------------------------------------------------------- action
    def vbet_frac(self, eq):
        """Value-bet size as a fraction of the pot, scaled by equity.

        Thin value (eq just over the threshold) bets small: their call
        range is wide, so a cheap bet still gets called by worse.  Thick
        value bets big to extract from those wide calls.
        """
        return max(0.30, min(VBET_MAX, VBET_BASE + VBET_SLOPE * (eq - VBET_REF)))

    def raise_amount(self, req, street, frac, history):
        """Legal raise-to (street total): int in [min_raise, max_raise]."""
        lo = int(req.get("min_raise", 2))
        hi = int(req.get("max_raise", lo))
        if hi < lo:
            hi = lo
        pot = int(req.get("pot", 0))
        to_call = max(0, int(req.get("to_call", 0)))
        opp_bet = int(req.get("opp_bet", 0))
        if street == "preflop":
            opp_last = _hist_raise_amount(history, street)
            target = round(2.6 * opp_last) if opp_last else PREFLOP_OPEN
        elif to_call > 0:
            target = opp_bet + max(2, round(frac * (pot + to_call)))
        else:
            target = max(lo, round(frac * pot)) if pot >= 4 else lo
        target = int(min(max(target, lo), hi))
        return {"type": "action", "action": "raise", "amount": target}

    def action(self, req):
        self.hand_id = int(req.get("hand_id") or self.hand_id)
        tl = req.get("time_left_ms")
        if isinstance(tl, int):
            self.tl = tl
        legal = req.get("legal_actions") or []
        if not legal:
            return safe_action(req)
        hc = req.get("hole_cards")
        if hc:
            self.hole = list(hc)   # forward-compat: if ever provided
        if not self.hole:
            return safe_action(req)

        street = req.get("street", "preflop")
        board = list(req.get("board") or [])
        history = req.get("history") or []
        to_call = max(0, int(req.get("to_call", 0)))
        pot = max(0, int(req.get("pot", 0)))

        # ---- equity -----------------------------------------------------
        if self.desperate():
            # Cannot afford even the minimum work: answer cheaply
            # rather than forfeit the match on a timeout.
            return safe_action(req)
        if len(self.hole) == 3:
            eqs = self.equity3(self.hole, board, self.stake_n(FLOP_N, pot))
            eq = float(eqs.max())
        else:
            extra = self._extra_out(self.hole, board)
            base = TURN_N if len(board) <= 4 else 0  # river = exact
            eq = self.equity2(self.hole, board, extra,
                              self.stake_n(base, pot) if base else 1)
            eq = float(eq)

        opp_raised_here = _opp_raised(history, street)
        reraise = opp_raised_here and _facing_reraise(history, street)

        # ---- facing no bet: bet value / bluff / check --------------------
        if to_call <= 0:
            if "raise" in legal:
                thr = BET_VALUE + self.bet_value_adj()
                if _opp_checked_last(history, street):
                    thr -= 0.03
                # open wider vs a heavy preflop folder (adaptive: with no
                # observed preflop folds the widening stays off)
                widen = 0.0
                if street == "preflop":
                    pf = self.street_fold_rate("preflop", need=8)
                    if pf is not None:
                        widen = PREFLOP_WIDEN * max(0.0, pf - 0.45)
                thr -= widen
                if eq >= thr:
                    frac = OPEN_FRAC if street == "preflop" \
                        else self.vbet_frac(eq)
                    return self.raise_amount(req, street, frac, history)
                if eq < 0.45 + widen \
                        and random.random() < self.bluff_freq(street):
                    frac = BLUFF_FRAC if street != "preflop" else OPEN_FRAC
                    return self.raise_amount(req, street, frac, history)
            if "check" in legal:
                return {"type": "action", "action": "check"}
            return safe_action(req)

        # ---- facing a bet: pot odds + range-adjusted equity -------------
        odds = to_call / (pot + to_call) if pot + to_call > 0 else 1.0
        eq_adj = (self.realized_eq(eq, street, reraise)
                  if opp_raised_here else eq)
        margin = CALL_MARGIN + self.call_margin_adj()
        if eq_adj >= odds + margin:
            if "raise" in legal and eq_adj >= RAISE_VALUE + self.bet_value_adj():
                return self.raise_amount(req, street,
                                         self.vbet_frac(eq_adj), history)
            if "call" in legal:
                # remember what equity we assumed when calling their bet;
                # settled against the actual result in end_hand()
                if opp_raised_here:
                    self.call_eq = (eq, street, odds, reraise)
                return {"type": "action", "action": "call"}
            if "raise" in legal:
                return self.raise_amount(req, street, RAISE_OVER_FRAC, history)
        if "fold" in legal:
            return {"type": "action", "action": "fold"}
        return safe_action(req)

    # ------------------------------------------------------------- discard
    def discard(self, req):
        tl = req.get("time_left_ms")
        if isinstance(tl, int):
            self.tl = tl
        cards = list(req.get("hole_cards") or [])
        if len(cards) != 3:
            return safe_discard(req)
        hole = self.hole if len(self.hole) == 3 and set(self.hole) == set(cards) \
            else cards
        board = list(req.get("board") or [])
        pot = max(0, int(req.get("pot", 0)))
        if self.desperate():
            # No time for even the minimum work: shed the lowest card
            # (the engine's own default) instead of timing out.
            return safe_discard(req)
        # eqs[i] corresponds to keeping (hole[a], hole[b]) -> discarding the
        # third card; pairs are (0,1),(0,2),(1,2) so discarded index = 2,1,0.
        eqs = self.equity3(hole, board, self.stake_n(FLOP_N, pot))
        best = float(eqs.max())
        cands = [i for i in range(3) if float(eqs[i]) >= best - CLOSE_BAND]
        discard_idx = [2, 1, 0]
        # among statistically tied keeps: shed the LOWEST card (safe default)
        pick = min(cands, key=lambda i: (
            RANKS.index(hole[discard_idx[i]][0]),
            SUITS.index(hole[discard_idx[i]][1])))
        return {"type": "discard", "card": hole[discard_idx[pick]]}

    def summary(self):
        s = self.st
        eq_avg = self.eq_ms / self.eq_calls if self.eq_calls else 0
        return (f"hands={s['hands']} net={s['net']} "
                f"eq_calls={self.eq_calls} eq_avg={eq_avg:.1f}ms "
                f"eq_total={self.eq_ms:.0f}ms tl_left={self.tl}")


# ------------------------------------------------------------- message loop
def main():
    bot = Bot()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            log("WARN: unparseable engine line ignored")
            continue
        if not isinstance(msg, dict):
            continue

        mtype = msg.get("type")
        if mtype == "match_end":
            log(f"match_end reason={msg.get('reason')} | {bot.summary()}")
            break
        if mtype not in ("action_request", "discard_request"):
            try:
                bot.observe(msg)
            except Exception:
                log_err(f"ERROR observing {mtype}:")
                traceback.print_exc(file=sys.stderr)
            continue

        try:
            bot.reply_t0 = time.perf_counter()   # watchdog: reply elapsed
            if mtype == "action_request":
                reply = bot.action(msg)
                reply = validate_reply(reply, "action", msg)
            else:
                reply = bot.discard(msg)
                reply = validate_reply(reply, "discard", msg)
            if reply is None:
                reply = (safe_action(msg) if mtype == "action_request"
                         else safe_discard(msg))
        except Exception:
            log_err(f"ERROR deciding for {mtype}:")
            traceback.print_exc(file=sys.stderr)
            reply = (safe_action(msg) if mtype == "action_request"
                     else safe_discard(msg))

        try:
            print(json.dumps(reply), flush=True)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            print(json.dumps(safe_action(msg)
                             if mtype == "action_request"
                             else safe_discard(msg)), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Outer rescue: keep answering correctly instead of timing out.
        traceback.print_exc(file=sys.stderr)
        for line in sys.stdin:
            try:
                m = json.loads(line)
                t = m.get("type")
                if t == "match_end":
                    break
                if t == "action_request":
                    print(json.dumps(safe_action(m)), flush=True)
                elif t == "discard_request":
                    print(json.dumps(safe_discard(m)), flush=True)
            except Exception:
                log_err("ERROR in rescue loop:")
                traceback.print_exc(file=sys.stderr)
                continue
        sys.exit(0)
