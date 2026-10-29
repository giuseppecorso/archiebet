"""Prova D164: pi-rating e gradient boosting come terza previsione, sopra lo studio di oggi (gol del mercato, D163).

Due modelli di gradient boosting con perdita di Poisson (gol di casa, gol dell'ospite), addestrati a finestra crescente:
per prevedere una stagione si usano solo le stagioni prima. Ingressi: forze pi delle due squadre (prima della partita),
differenza reti attesa, gol attesi del mercato (vuoti se mancano), campionato.
"""

import math
from collections.abc import Mapping, Sequence
from datetime import timedelta

from app.forecast import study_backtest as bt
from app.forecast.pi_ratings import PiRatings

TARGETS = (*bt.TUNING, *bt.CONFIRMATION)


def _market(market: Mapping[tuple[str, int, int], tuple[float, float]], g: bt.G) -> tuple[float, float] | None:
    return next((market[k] for d in (0, -1, 1) if (k := ((g.date + timedelta(days=d)).date().isoformat(), g.home, g.away)) in market), None)


def features(games: Sequence[bt.G], market: Mapping[tuple[str, int, int], tuple[float, float]]) -> dict[int, list[float]]:
    """Ingressi di ogni partita, calcolati prima del calcio d'inizio (le forze pi si aggiornano dopo)."""
    leagues = {lg: i for i, lg in enumerate(sorted({g.league for g in games}))}
    pi, out = PiRatings(), {}
    for g in sorted(games, key=lambda g: g.date):
        s = pi.state(g.home, g.away)
        mk = _market(market, g)
        out[g.id] = [s.home_h, s.home_a, s.away_h, s.away_a, s.expected_diff,
                     mk[0] if mk else math.nan, mk[1] if mk else math.nan, float(leagues[g.league])]  # fmt: skip
        pi.update(g.home, g.away, g.hg, g.ag)
    return out


def predictions(games: Sequence[bt.G], feats: Mapping[int, list[float]]) -> dict[int, tuple[float, float]]:
    """Gol attesi (casa, ospite) del gradient boosting per le stagioni da valutare, ognuna con un modello addestrato
    solo sulle stagioni precedenti."""
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingRegressor

    out = {}
    for target in TARGETS:
        train = [g for g in games if g.season < target]
        test = [g for g in games if g.season == target]
        if not train or not test:
            continue
        x = np.array([feats[g.id] for g in train])
        empty = np.isnan(x).all(axis=0)  # una colonna tutta vuota (es. niente quote) manda in errore la libreria: diventa 0
        x[:, empty] = 0.0
        models = []
        for goals in ([g.hg for g in train], [g.ag for g in train]):
            m = HistGradientBoostingRegressor(loss="poisson", categorical_features=[7], random_state=0)
            models.append(m.fit(x, np.array(goals, dtype=float)))
        xt = np.array([feats[g.id] for g in test])
        xt[:, empty] = 0.0
        for g, lam, mu in zip(test, models[0].predict(xt), models[1].predict(xt)):
            out[g.id] = (float(lam), float(mu))
    return out
