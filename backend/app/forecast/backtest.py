"""Backtest walk-forward: si prevede ogni partita usando SOLO le partite giocate prima (principio 3).

Come funziona: si va avanti a blocchi di una settimana. A ogni blocco il modello si ristima sulle partite
finite prima della mezzanotte del primo giorno del blocco (ultimi `window_days` giorni, pesate nel tempo)
e prevede tutte le partite del blocco. Un unico modello per A, B e C insieme: le squadre promosse e
retrocesse collegano le categorie.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import numpy as np

from app.forecast.data import Game
from app.forecast.elo import EloTimeline, run_elo
from app.forecast.markets import markets
from app.forecast.metrics import brier, calibration, expected_calibration_error, log_loss, outcome_index, rps
from app.forecast.model import ModelConfig, fit_at
from app.forecast.vault import VAULT_MARKER, ensure_can_evaluate


@dataclass(frozen=True)
class Prediction:
    match_id: int
    competition_id: int
    season: str
    outcome: int  # 0 = 1, 1 = X, 2 = 2
    total_goals: int
    both_scored: bool
    p_1x2: tuple[float, float, float]
    p_over25: float
    p_gg: float


@dataclass
class WalkForwardResult:
    predictions: list[Prediction]
    skipped: int  # partite non previste perché una squadra non ha storia nella finestra
    fits: int


def walk_forward(
    games: Sequence[Game],
    eval_seasons: Iterable[str],
    config: ModelConfig = ModelConfig(),
    vault_marker: Path = VAULT_MARKER,
    progress: Callable[[int, int], None] | None = None,
) -> WalkForwardResult:
    eval_seasons = set(eval_seasons)
    ensure_can_evaluate(eval_seasons, vault_marker)
    kickoffs = [g.kickoff_at for g in games]
    if kickoffs != sorted(kickoffs):
        raise ValueError("Le partite devono essere in ordine di calcio d'inizio")
    targets = [g for g in games if g.season in eval_seasons]
    # L'Elo scorre tutte le partite, ma a ogni blocco si leggono solo i rating precedenti all'inizio del blocco
    timeline = EloTimeline(games, run_elo(games, config.elo)) if config.elo_prior else None

    predictions: list[Prediction] = []
    skipped = fits = 0
    i = 0
    while i < len(targets):
        start = targets[i].kickoff_at.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=config.refit_every_days)
        block = []
        while i < len(targets) and targets[i].kickoff_at < end:
            block.append(targets[i])
            i += 1

        # Allenamento: solo partite iniziate prima di `start`
        fit = fit_at(
            games,
            kickoffs,
            start,
            config,
            extra_teams={t for g in block for t in (g.home_id, g.away_id)},
            rating_at=(lambda t: timeline.rating_at(t, start)) if timeline else None,
        )
        if fit is None:
            skipped += len(block)
            continue
        fits += 1
        for g in block:
            if not (fit.has_team(g.home_id) and fit.has_team(g.away_id)):
                skipped += 1
                continue
            mk = markets(fit.score_matrix(g.home_id, g.away_id))
            predictions.append(
                Prediction(
                    match_id=g.match_id,
                    competition_id=g.competition_id,
                    season=g.season,
                    outcome=outcome_index(g.home_goals, g.away_goals),
                    total_goals=g.home_goals + g.away_goals,
                    both_scored=g.home_goals > 0 and g.away_goals > 0,
                    p_1x2=(mk["1X2"]["1"], mk["1X2"]["X"], mk["1X2"]["2"]),
                    p_over25=mk["OU2.5"]["over"],
                    p_gg=mk["GG"]["yes"],
                )
            )
        if progress:
            progress(i, len(targets))
    return WalkForwardResult(predictions, skipped, fits)


@dataclass(frozen=True)
class Scores:
    n: int
    log_loss: float
    brier: float
    rps: float
    ece: float  # errore di calibrazione medio sulle tre probabilità 1/X/2
    # Stesse misure per il mercato di chiusura (D48) sulle partite dove c'è, e per il modello sulle stesse
    n_market: int
    model_log_loss_on_market: float | None
    market_log_loss: float | None


def score(preds: Sequence[Prediction], market: dict[int, tuple[float, float, float]]) -> Scores:
    probs = np.array([p.p_1x2 for p in preds])
    outcomes = np.array([p.outcome for p in preds])
    hits = np.eye(3)[outcomes]
    ece = float(np.mean([expected_calibration_error(calibration(probs[:, k], hits[:, k])) for k in range(3)]))
    with_market = [i for i, p in enumerate(preds) if p.match_id in market]
    if with_market:
        mprobs = np.array([market[preds[i].match_id] for i in with_market])
        model_ll, market_ll = log_loss(probs[with_market], outcomes[with_market]), log_loss(mprobs, outcomes[with_market])
    else:
        model_ll = market_ll = None
    return Scores(
        n=len(preds),
        log_loss=log_loss(probs, outcomes),
        brier=brier(probs, outcomes),
        rps=rps(probs, outcomes),
        ece=ece,
        n_market=len(with_market),
        model_log_loss_on_market=model_ll,
        market_log_loss=market_ll,
    )


def score_by(
    preds: Sequence[Prediction], market: dict[int, tuple[float, float, float]], key: Callable[[Prediction], object]
) -> dict[object, Scores]:
    groups: dict[object, list[Prediction]] = defaultdict(list)
    for p in preds:
        groups[key(p)].append(p)
    return {k: score(v, market) for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))}


@dataclass(frozen=True)
class PairedComparison:
    n: int  # partite previste da entrambe le varianti
    mean_diff: float  # log loss di B − log loss di A, in media: negativo = B prevede meglio
    std_error: float

    @property
    def b_is_better(self) -> bool:
        """Prova del nove (principio 5): B migliora A oltre il rumore (2 errori standard)."""
        return self.mean_diff < -2 * self.std_error


def compare(a: Sequence[Prediction], b: Sequence[Prediction]) -> PairedComparison:
    """Confronto partita per partita sulle sole partite previste da entrambe le varianti."""
    a_by_id = {p.match_id: p for p in a}
    pairs = [(a_by_id[p.match_id], p) for p in b if p.match_id in a_by_id]
    if not pairs:
        raise ValueError("Nessuna partita in comune tra le due varianti")
    diff = np.array([-np.log(pb.p_1x2[pb.outcome]) + np.log(pa.p_1x2[pa.outcome]) for pa, pb in pairs])
    return paired(diff)


def paired(diff: np.ndarray) -> PairedComparison:
    """Media e errore standard delle differenze partita per partita (B − A)."""
    se = float(diff.std(ddof=1) / np.sqrt(len(diff))) if len(diff) > 1 else float("inf")
    return PairedComparison(len(diff), float(diff.mean()), se)
