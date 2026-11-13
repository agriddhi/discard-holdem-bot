"""Fast vectorized hand evaluation + Monte Carlo equity for Discard Hold'em.

Card id: rank_idx * 4 + suit_idx, rank_idx 0..12 ("23456789TJQKA"), suit 0..3 ("shdc").
Scores are packed int64: cat * 16^5 + five tiebreak nibbles (higher is better).
"""
import numpy as np

RANKS = "23456789TJQKA"
SUITS = "shdc"
_DECK = np.arange(52, dtype=np.int64)


def cid(card):
    return RANKS.index(card[0]) * 4 + SUITS.index(card[1])


def cstr(cid_):
    return RANKS[cid_ // 4] + SUITS[cid_ % 4]


def _straight_high(present):
    """(N,13) bool -> (N,) highest straight top index (0..12) or -1. Ace-low = 3."""
    w = (present[:, :-4] & present[:, 1:-3] & present[:, 2:-2]
         & present[:, 3:-1] & present[:, 4:])              # (N,9), window j = ranks j..j+4
    sh = np.where(w, np.arange(4, 13, dtype=np.int8), -1).max(axis=1)
    wheel = present[:, [12, 0, 1, 2, 3]].all(1)
    return np.where(wheel & (sh < 0), 3, sh)


def _top_idx(cond, k, avail):
    """Top-k rank indices by rank desc among cond&avail, (N,k) int8.

    Valid keys are the rank indices themselves (all distinct), so argmax
    pops them one at a time; a fresh -1 mask is mutated in place. Exhausted
    slots come back as 0 (unread by callers: every hand category that gets
    selected provably has enough cards available).
    """
    key = np.where(cond & avail, np.arange(13, dtype=np.int16), -1)
    out = np.empty((key.shape[0], k), np.int8)
    rows = np.arange(key.shape[0])
    for j in range(k):
        idx = key.argmax(1)
        out[:, j] = idx
        key[rows, idx] = -1
    return out


def eval7(ranks, suits):
    """Best 5 of 7. ranks/suits (N,7) int -> (N,) int64 scores."""
    n = ranks.shape[0]
    rank_oh = (ranks[:, :, None] == np.arange(13))       # (N,7,13)
    rc = rank_oh.sum(1)                                   # (N,13)
    sc = (suits[:, :, None] == np.arange(4)).sum(1)       # (N,4)
    pr = rc > 0
    flush = sc.max(1) >= 5
    fs = sc.argmax(1)
    in_flush = (suits == fs[:, None]) & flush[:, None]
    fc = (rank_oh & in_flush[:, :, None]).sum(1)          # flush-suit counts (N,13)

    n_trips = (rc == 3).sum(1)
    n_pairs = (rc == 2).sum(1)
    has_quad = (rc == 4).any(1)
    sh = _straight_high(pr)
    sfh = _straight_high(fc > 0)
    is_sf = flush & (sfh >= 0)

    rows = np.arange(n)
    top5 = _top_idx(np.ones_like(pr), 5, pr)
    fl5 = _top_idx(fc > 0, 5, fc > 0)
    q = _top_idx(rc == 4, 1, pr)
    qk = _top_idx(pr & (rc != 4), 1, pr)
    t1 = _top_idx(rc == 3, 1, pr)
    ge2e = rc >= 2
    ge2e[rows, t1[:, 0]] = False
    fhp = _top_idx(ge2e, 1, pr)
    is_fh = (n_trips > 0) & ge2e.any(1)
    tk = _top_idx(pr & (rc != 3), 2, pr)
    p2 = _top_idx(rc == 2, 2, pr)
    tpk_m = pr.copy()
    tpk_m[rows, p2[:, 0]] = False
    tpk_m[rows, p2[:, 1]] = False
    tpk = _top_idx(np.ones_like(pr), 1, tpk_m)
    p1 = _top_idx(rc == 2, 1, pr)
    pk_m = pr.copy()
    pk_m[rows, p1[:, 0]] = False
    pk = _top_idx(np.ones_like(pr), 3, pk_m)

    z = np.zeros(n, np.int8)

    def pack(cat, *tbs):
        s = np.full(n, cat, np.int64)
        for t in tbs:
            s = s * 16 + t
        return s

    conds = [is_sf, has_quad, is_fh, flush & ~is_sf, (sh >= 0) & ~flush,
             n_trips >= 1, n_pairs >= 2, n_pairs >= 1, np.ones(n, bool)]
    choices = [
        pack(8, sfh, z, z, z, z),
        pack(7, q[:, 0], qk[:, 0], z, z, z),
        pack(6, t1[:, 0], fhp[:, 0], z, z, z),
        pack(5, fl5[:, 0], fl5[:, 1], fl5[:, 2], fl5[:, 3], fl5[:, 4]),
        pack(4, sh, z, z, z, z),
        pack(3, t1[:, 0], tk[:, 0], tk[:, 1], z, z),
        pack(2, p2[:, 0], p2[:, 1], tpk[:, 0], z, z),
        pack(1, p1[:, 0], pk[:, 0], pk[:, 1], pk[:, 2], z),
        pack(0, top5[:, 0], top5[:, 1], top5[:, 2], top5[:, 3], top5[:, 4]),
    ]
    return np.select(conds, choices, default=choices[-1])


def _best_scores(ids, board):
    """ids (n,k) k in {2,3}, board (n,5) -> (n,) score; k=3 = oracle discard.

    The 3-card case evaluates all three keep-pairs in ONE eval7 call over a
    (3n,7) array instead of three separate (n,7) calls (less numpy overhead,
    one pass over shared board columns).
    """
    n = ids.shape[0]
    br, bs = board // 4, board % 4
    if ids.shape[1] == 2:
        r = np.empty((n, 7), np.int64)
        s = np.empty((n, 7), np.int64)
        r[:, :5], s[:, :5] = br, bs
        r[:, 5:], s[:, 5:] = ids // 4, ids % 4
        return eval7(r, s)
    r = np.empty((3 * n, 7), np.int64)
    s = np.empty((3 * n, 7), np.int64)
    for ci, (a, b) in enumerate(((0, 1), (0, 2), (1, 2))):
        lo, hi = ci * n, (ci + 1) * n
        r[lo:hi, :5], s[lo:hi, :5] = br, bs
        r[lo:hi, 5], r[lo:hi, 6] = ids[:, a] // 4, ids[:, b] // 4
        s[lo:hi, 5], s[lo:hi, 6] = ids[:, a] % 4, ids[:, b] % 4
    return eval7(r, s).reshape(3, n).max(axis=0)


def _sample_unknown(deck, k, n):
    """n uniform k-subsets without replacement, each in a random order."""
    r = np.random.random((n, len(deck)))
    part = np.argpartition(r, k, axis=1)[:, :k]           # k columns with smallest r
    vals = np.take_along_axis(r, part, axis=1)
    order = np.argsort(vals, axis=1)                      # iid -> uniform permutation
    return deck[np.take_along_axis(part, order, axis=1)]


def _exact_river(my, board, extra=()):
    """Exact equity on the river vs every opponent 2-card holding."""
    known = np.concatenate([my, board, np.asarray(extra, np.int64).ravel()])
    deck = _DECK[~np.isin(_DECK, known)]
    ii, jj = np.triu_indices(len(deck), 1)
    opp = np.stack([deck[ii], deck[jj]], 1)
    opp_s = _best_scores(opp, np.broadcast_to(board, (len(opp), 5)))
    mine = float(_best_scores(my[None, :], board[None, :])[0])
    return float((opp_s < mine).mean() + 0.5 * (opp_s == mine).mean())


def equity_mc(my_ids, board_ids, opp_n, n=1000, per_keep=False, known_extra=()):
    """Equity vs opponent holding opp_n unknown cards (oracle discard if 3).

    board_ids: known board (0..5 cards). known_extra: cards out of play
    (e.g. the opponent's exposed discard) excluded from the deck.
    Returns float in [0,1], or (eqs(3,), best_i) for per_keep with 3-card hand.
    """
    my = np.asarray(my_ids, np.int64).ravel()
    board = np.asarray(board_ids, np.int64).ravel()
    extra_ids = np.asarray(known_extra, np.int64).ravel()
    to_come = 5 - len(board)

    if to_come == 0 and opp_n == 2:
        if per_keep and len(my) == 3:
            eqs = np.empty(3)
            for i, (a, b) in enumerate(((0, 1), (0, 2), (1, 2))):
                eqs[i] = _exact_river(my[[a, b]], board, extra_ids)
            return eqs, int(eqs.argmax())
        return _exact_river(my, board, extra_ids)

    known = np.concatenate([my, board, extra_ids])
    deck = _DECK[~np.isin(_DECK, known)]
    samp = _sample_unknown(deck, opp_n + to_come, n)
    opp = samp[:, :opp_n]
    extra = samp[:, opp_n:]
    board_full = (np.concatenate([np.broadcast_to(board, (n, len(board))), extra], 1)
                  if to_come else np.broadcast_to(board, (n, 5)))

    opp_s = _best_scores(opp, board_full)
    if per_keep and len(my) == 3:
        # all three keeps share the same samples -> paired, low-noise comparison
        keep = np.concatenate([np.broadcast_to(my[list(p)], (n, 2))
                               for p in ((0, 1), (0, 2), (1, 2))])          # (3n,2)
        mine = _best_scores(keep, np.tile(board_full, (3, 1))).reshape(3, n)
        opp3 = np.tile(opp_s, (3, 1))
        eqs = ((mine > opp3).mean(1) + 0.5 * (mine == opp3).mean(1))
        return eqs, int(eqs.argmax())
    mine = _best_scores(np.broadcast_to(my, (n, len(my))), board_full)
    return float((mine > opp_s).mean() + 0.5 * (mine == opp_s).mean())
