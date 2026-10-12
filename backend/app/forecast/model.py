"""Il modello di Archie in un punto solo: configurazione e stima "a un certo istante".

Lo usano sia il backtest (ristima settimanale nel passato) sia le previsioni dell'app (ristima adesso),
così ciò che si misura nel backtest è esattamente ciò che si mostra.
"""

from bisect import bisect_left
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.forecast.data import Game
from app.forecast.dixon_coles import DixonColesFit, fit_dixon_coles, time_decay_weights
from app.forecast.elo import EloParams

MODEL_VERSION = "dc-elo-1"  # cambia quando cambia il modello: le previsioni salvate si rifanno


@dataclass(frozen=True)
class ModelConfig:
    # Valori tarati sul 2016/17-2021/22 e confermati sul 2022/23-2024/25 (D50-D51)
    xi_per_day: float = 0.002  # peso dimezzato in circa 1 anno (ln 2 / 0,002 ≈ 347 giorni)
    ridge: float = 8.0  # in "partite equivalenti" verso il punto di partenza
    window_days: int = 3 * 365
    refit_every_days: int = 7
    elo_prior: bool = True  # punto di partenza del ridge = forza Elo invece della media (prova del nove superata)
    elo: EloParams = EloParams()


def fit_at(
    games: Sequence[Game],
    kickoffs: Sequence[datetime],
    when: datetime,
    config: ModelConfig,
    extra_teams: Iterable[int] = (),
    rating_at: Callable[[int], float] | None = None,
) -> DixonColesFit | None:
    """Stima il modello con le sole partite iniziate prima di `when` (ultimi `window_days` giorni).

    `games` e `kickoffs` sono in ordine di calcio d'inizio. Con l'Elo, `rating_at(squadra)` dà il rating
    della squadra a `when` e le `extra_teams` (anche senza partite) vengono stimate dal loro rating.
    Restituisce None se non c'è nessuna partita da cui imparare.
    """
    train = games[bisect_left(kickoffs, when - timedelta(days=config.window_days)) : bisect_left(kickoffs, when)]
    if not train:
        return None
    strength, extra = None, set()
    if config.elo_prior:
        if rating_at is None:
            raise ValueError("Con l'Elo serve il rating di ogni squadra")
        extra = set(extra_teams)
        teams = extra | {t for g in train for t in (g.home_id, g.away_id)}
        strength = {t: rating_at(t) / 100 for t in teams}
    return fit_dixon_coles(
        [g.home_id for g in train],
        [g.away_id for g in train],
        [g.home_goals for g in train],
        [g.away_goals for g in train],
        weights=time_decay_weights([g.kickoff_at for g in train], when, config.xi_per_day),
        ridge=config.ridge,
        strength=strength,
        extra_teams=extra,
    )
