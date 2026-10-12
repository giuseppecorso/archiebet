"""Prova del nove dei fattori CONTRO IL MERCATO (D53), su Serie A e B.

Base: probabilità di apertura Pinnacle senza margine (ciò che il mercato sa quando si gioca).
Per ogni fattore: mercato ricalibrato con e senza il fattore, stimato stagione per stagione sul passato.
Il fattore passa se migliora la log loss oltre 2 errori standard. In più: CLV delle giocate con valore
calcolate con le probabilità corrette, alla quota di apertura (Pinnacle e bet365) contro la chiusura di riferimento.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.forecast.backtest import PairedComparison, Prediction, paired
from app.forecast.data import Game, Odds
from app.forecast.market_model import MarketRow, walk_forward_by_season
from app.forecast.vault import VAULT_MARKER, ensure_can_evaluate

SELECTIONS = ("1", "X", "2")


@dataclass(frozen=True)
class Clv:
    n: int
    mean: float
    std_error: float


@dataclass(frozen=True)
class FactorResult:
    name: str
    n: int
    log_loss: float
    vs_baseline: PairedComparison | None  # rispetto al mercato ricalibrato senza fattori
    clv_pinnacle: Clv | None  # giocate con valore alla quota Pinnacle di apertura
    clv_bet365: Clv | None  # giocate con valore alla quota bet365 di apertura

    @property
    def passes(self) -> bool:
        return self.vs_baseline is not None and self.vs_baseline.b_is_better


def market_rows(games: Sequence[Game], opening_fair: Odds, closing_fair: Odds) -> list[MarketRow]:
    """Partite di A e B con apertura Pinnacle e chiusura di riferimento (per poter misurare il CLV)."""
    rows = []
    for g in games:
        if g.tier not in (1, 2):
            continue
        op, cl = opening_fair.get(g.match_id, {}).get("1X2"), closing_fair.get(g.match_id, {}).get("1X2")
        if op and cl:
            outcome = 0 if g.home_goals > g.away_goals else 1 if g.home_goals == g.away_goals else 2
            rows.append(MarketRow(g.match_id, g.season, outcome, tuple(op[s] for s in SELECTIONS)))
    return rows


def model_disagreement(rows: Sequence[MarketRow], model: Sequence[Prediction]) -> dict[int, list[float]]:
    """Quanto il modello di Archie vede la casa più forte del mercato: log(p1/p2) modello − log(p1/p2) mercato."""
    by_id = {p.match_id: p for p in model}
    out = {}
    for r in rows:
        p = by_id.get(r.match_id)
        if p:
            out[r.match_id] = [np.log(p.p_1x2[0] / p.p_1x2[2]) - np.log(r.p_open[0] / r.p_open[2])]
    return out


def clv_of_value_bets(probs: Mapping[int, np.ndarray], offered: Odds, closing_fair: Odds, threshold: float) -> Clv | None:
    values = []
    for match_id, p in probs.items():
        prices, fair = offered.get(match_id, {}).get("1X2"), closing_fair.get(match_id, {}).get("1X2")
        if not prices or not fair:
            continue
        for k, sel in enumerate(SELECTIONS):
            if p[k] * prices[sel] - 1 >= threshold:
                values.append(prices[sel] * fair[sel] - 1)
    if not values:
        return None
    v = np.array(values)
    return Clv(len(v), float(v.mean()), float(v.std(ddof=1) / np.sqrt(len(v))) if len(v) > 1 else float("inf"))


def run(
    rows: Sequence[MarketRow],
    factors: Mapping[str, Mapping[int, Sequence[float]]],
    eval_seasons: Sequence[str],
    offered_pinnacle: Odds,
    offered_bet365: Odds,
    closing_fair: Odds,
    threshold: float = 0.02,
    vault_marker: Path = VAULT_MARKER,
) -> list[FactorResult]:
    """Valuta il mercato grezzo, quello ricalibrato e ogni fattore sulle stesse partite."""
    ensure_can_evaluate(eval_seasons, vault_marker)
    eval_ids = {r.match_id for r in rows if r.season in set(eval_seasons)}
    by_id = {r.match_id: r for r in rows}

    def loss(probs: Mapping[int, np.ndarray]) -> dict[int, float]:
        return {m: -float(np.log(probs[m][by_id[m].outcome])) for m in probs}

    raw = {m: np.array(by_id[m].p_open) for m in eval_ids}
    baseline = walk_forward_by_season(rows, {}, eval_seasons, n_features=1)
    variants: list[tuple[str, dict[int, np.ndarray]]] = [("Mercato di apertura (grezzo)", raw), ("Mercato ricalibrato", baseline)]
    for name, feats in factors.items():
        variants.append((name, walk_forward_by_season(rows, feats, eval_seasons, n_features=len(next(iter(feats.values()), [0])))))

    base_loss = loss(baseline)
    results = []
    for name, probs in variants:
        ll = loss(probs)
        common = [m for m in ll if m in base_loss]
        comparison = paired(np.array([ll[m] - base_loss[m] for m in common])) if name != "Mercato ricalibrato" else None
        results.append(
            FactorResult(
                name=name,
                n=len(ll),
                log_loss=float(np.mean(list(ll.values()))),
                vs_baseline=comparison,
                clv_pinnacle=clv_of_value_bets(probs, offered_pinnacle, closing_fair, threshold),
                clv_bet365=clv_of_value_bets(probs, offered_bet365, closing_fair, threshold),
            )
        )
    return results



def as_features(values: Mapping[int, float]) -> dict[int, list[float]]:
    return {m: [v] for m, v in values.items()}
