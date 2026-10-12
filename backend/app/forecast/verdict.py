"""Verdetto sulla stagione 2025/26 in cassaforte: si calcola UNA volta, a cassaforte aperta, con criteri
fissati prima di guardare (D58). Serie A e B: modello e radar. Serie C: solo il modello, quando ci sono i dati.

Criteri (D58):
1. Modello calibrato: errore di calibrazione medio 1/X/2 ≤ 3%.
2. Modello non peggiore del backtest: distanza dalla log loss del mercato di chiusura ≤ 0,03.
3. Radar (motore di A e B, D57): CLV medio delle giocate con valore ≥ 2% alla quota bet365 di apertura,
   contro la chiusura di riferimento, positivo oltre 2 errori standard.
Se 3 passa, i suggerimenti del radar escono dalla prova; il modello resta "in prova" se 1 o 2 non passano.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.forecast.backtest import Scores, score, walk_forward
from app.forecast.data import Game, Odds, reference_1x2
from app.forecast.factor_test import Clv, clv_of_value_bets
from app.forecast.model import ModelConfig
from app.forecast.vault import VAULT_FIRST_SEASON, VAULT_MARKER, VaultLockedError, vault_is_open

MAX_CALIBRATION_ERROR = 0.03
MAX_GAP_TO_MARKET = 0.03
RADAR_THRESHOLD = 0.02


@dataclass(frozen=True)
class Verdict:
    seasons: list[str]
    model: Scores
    radar: Clv | None

    @property
    def model_calibrated(self) -> bool:
        return self.model.ece <= MAX_CALIBRATION_ERROR

    @property
    def model_close_to_market(self) -> bool:
        m = self.model
        return m.market_log_loss is not None and m.model_log_loss_on_market - m.market_log_loss <= MAX_GAP_TO_MARKET

    @property
    def radar_passes(self) -> bool:
        return self.radar is not None and self.radar.mean > 2 * self.radar.std_error


def sharp_opening(opening_pinnacle: Odds, opening_betfair: Odds) -> Odds:
    """Probabilità giuste di apertura: Pinnacle, altrimenti Betfair Exchange (come D48 per la chiusura)."""
    return opening_betfair | opening_pinnacle


def compute(
    games: Sequence[Game],
    sharp_open_fair: Odds,
    offered_bet365: Odds,
    closing_fair: Odds,
    config: ModelConfig = ModelConfig(),
    vault_marker: Path = VAULT_MARKER,
) -> Verdict:
    if not vault_is_open(vault_marker):
        raise VaultLockedError("Il verdetto si calcola solo a cassaforte aperta: python -m app.cli open-vault")
    seasons = [VAULT_FIRST_SEASON]  # il 2026/27 serve alla simulazione dal vivo (Fase 4), non al verdetto
    preds = walk_forward(games, seasons, config, vault_marker=vault_marker).predictions
    ab = {g.match_id for g in games if g.tier in (1, 2) and g.season in seasons}
    radar_probs = {
        m: np.array([v["1X2"][s] for s in ("1", "X", "2")])
        for m, v in sharp_open_fair.items()
        if m in ab and "1X2" in v
    }
    return Verdict(
        seasons=seasons,
        model=score(preds, reference_1x2(closing_fair)),
        radar=clv_of_value_bets(radar_probs, offered_bet365, closing_fair, RADAR_THRESHOLD),
    )
