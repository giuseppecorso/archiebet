"""Rating Elo costruito da noi su tutte le partite di A, B e C (ClubElo non copre la Serie C).

Le categorie sono collegate solo dalle squadre promosse e retrocesse, che portano con sé il loro rating.
Ogni partita riceve il rating delle due squadre PRIMA del calcio d'inizio (principio 3).

Regole:
- risultato atteso della squadra di casa  E = 1 / (1 + 10^((R_fuori − R_casa − campo) / 400))
- dopo la partita  R += K · G · (S − E), con S = 1 / 0,5 / 0 e G che cresce con lo scarto di gol
- squadra mai vista: media di fine stagione della sua categoria meno un "malus matricola"
  (arriva da una categoria più bassa); se la categoria non ha ancora una stagione chiusa, il valore base
- a inizio stagione ogni rating si avvicina di una frazione alla media della categoria in cui gioca
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.forecast.data import Game


@dataclass(frozen=True)
class EloParams:
    k: float = 20.0
    home_advantage: float = 60.0
    tier_base: dict[int, float] = field(default_factory=lambda: {1: 1500.0, 2: 1350.0, 3: 1200.0})
    newcomer_penalty: float = 50.0
    season_regression: float = 0.0  # 0 = nessuna, 1 = tutti ripartono dalla media


def expected_home(home_rating: float, away_rating: float, home_advantage: float) -> float:
    return 1.0 / (1.0 + 10 ** ((away_rating - home_rating - home_advantage) / 400))


def goal_multiplier(goal_diff: int) -> float:
    """Peso dello scarto (formula del World Football Elo): 1 fino a un gol, 1,5 con due, poi (11+d)/8."""
    d = abs(goal_diff)
    if d <= 1:
        return 1.0
    if d == 2:
        return 1.5
    return (11 + d) / 8


@dataclass
class EloResult:
    pre_match: list[tuple[float, float]]  # (rating casa, rating fuori) prima di ogni partita, stesso ordine dell'input
    ratings: dict[int, float]  # rating attuale dopo l'ultima partita


def run_elo(games: Sequence[Game], params: EloParams = EloParams()) -> EloResult:
    """Scorre le partite in ordine di calcio d'inizio e restituisce i rating prima di ognuna."""
    if any(b.kickoff_at < a.kickoff_at for a, b in zip(games, games[1:])):
        raise ValueError("Le partite devono essere in ordine di calcio d'inizio")

    ratings: dict[int, float] = {}
    team_season: dict[int, str] = {}
    tier_seasons: dict[int, list[str]] = defaultdict(list)  # stagioni viste per categoria, in ordine
    season_table: dict[tuple[int, str], dict[int, float]] = defaultdict(dict)  # ultimo rating di ogni squadra
    pre_match: list[tuple[float, float]] = []

    def last_season_mean(tier: int, season: str) -> float | None:
        """Media dei rating di fine stagione precedente della categoria (None se non esiste)."""
        seasons = tier_seasons[tier]
        idx = seasons.index(season)
        if idx == 0:
            return None
        table = season_table[(tier, seasons[idx - 1])]
        return sum(table.values()) / len(table)

    def enter(team: int, game: Game) -> None:
        """Rating della squadra alla sua prima partita della stagione."""
        mean = last_season_mean(game.tier, game.season)
        if team not in ratings:
            ratings[team] = params.tier_base[game.tier] if mean is None else mean - params.newcomer_penalty
        elif mean is not None:
            ratings[team] += params.season_regression * (mean - ratings[team])
        team_season[team] = game.season

    for g in games:
        if g.season not in tier_seasons[g.tier]:
            tier_seasons[g.tier].append(g.season)
        for team in (g.home_id, g.away_id):
            if team_season.get(team) != g.season:
                enter(team, g)

        rh, ra = ratings[g.home_id], ratings[g.away_id]
        pre_match.append((rh, ra))
        score = 1.0 if g.home_goals > g.away_goals else 0.5 if g.home_goals == g.away_goals else 0.0
        delta = params.k * goal_multiplier(g.home_goals - g.away_goals) * (score - expected_home(rh, ra, params.home_advantage))
        ratings[g.home_id], ratings[g.away_id] = rh + delta, ra - delta
        table = season_table[(g.tier, g.season)]
        table[g.home_id], table[g.away_id] = ratings[g.home_id], ratings[g.away_id]

    return EloResult(pre_match=pre_match, ratings=ratings)
