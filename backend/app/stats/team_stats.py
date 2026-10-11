"""Statistiche di squadra calcolate dal codice (principio 4). Funzioni pure su risultati già giocati.

Regola anti-futuro (principio 3): chi chiama passa solo partite giocate PRIMA del momento di riferimento;
le funzioni qui lo verificano comunque con il parametro `before`.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Result:
    """Una partita finita, ridotta a ciò che serve alle statistiche."""

    match_id: int
    kickoff_at: datetime
    home_id: int
    away_id: int
    home_goals: int
    away_goals: int
    home_shots: int | None = None
    away_shots: int | None = None
    home_shots_on_target: int | None = None
    away_shots_on_target: int | None = None
    home_corners: int | None = None
    away_corners: int | None = None
    home_xg: Decimal | None = None
    away_xg: Decimal | None = None

    def side(self, team_id: int) -> str:
        if team_id == self.home_id:
            return "home"
        if team_id == self.away_id:
            return "away"
        raise ValueError(f"La squadra {team_id} non gioca la partita {self.match_id}")

    def goals_for(self, team_id: int) -> int:
        return self.home_goals if self.side(team_id) == "home" else self.away_goals

    def goals_against(self, team_id: int) -> int:
        return self.away_goals if self.side(team_id) == "home" else self.home_goals

    def outcome(self, team_id: int) -> str:
        """"V" vittoria, "N" pareggio, "P" sconfitta, dal punto di vista della squadra."""
        diff = self.goals_for(team_id) - self.goals_against(team_id)
        return "V" if diff > 0 else "N" if diff == 0 else "P"

    def points(self, team_id: int) -> int:
        return {"V": 3, "N": 1, "P": 0}[self.outcome(team_id)]


def _played_by(results: Iterable[Result], team_id: int, before: datetime, venue: str | None = None) -> list[Result]:
    """Partite della squadra prima di `before`, dalla più recente; venue "home"/"away" per filtrare."""
    games = [r for r in results if r.kickoff_at < before and team_id in (r.home_id, r.away_id)]
    if venue:
        games = [r for r in games if r.side(team_id) == venue]
    return sorted(games, key=lambda r: r.kickoff_at, reverse=True)


def form(results: Iterable[Result], team_id: int, before: datetime, n: int = 5) -> list[tuple[str, Result]]:
    """Ultime n partite: (esito, partita), dalla più recente."""
    return [(r.outcome(team_id), r) for r in _played_by(results, team_id, before)[:n]]


def _avg(values: Sequence[float | int | Decimal | None]) -> float | None:
    present = [float(v) for v in values if v is not None]
    return round(sum(present) / len(present), 2) if present else None


def _share(flags: Sequence[bool]) -> float | None:
    return round(sum(flags) / len(flags), 3) if flags else None


@dataclass(frozen=True)
class TeamSummary:
    played: int
    points_per_game: float | None
    goals_for: float | None
    goals_against: float | None
    shots_for: float | None
    shots_on_target_for: float | None
    corners_for: float | None
    xg_for: float | None
    xg_against: float | None
    clean_sheets: float | None  # quota di partite senza gol subiti (0-1)
    over_2_5: float | None  # quota di partite con almeno 3 gol totali
    both_scored: float | None  # quota di partite in cui hanno segnato entrambe


def summary(results: Iterable[Result], team_id: int, before: datetime, venue: str | None = None) -> TeamSummary:
    games = _played_by(results, team_id, before, venue)

    def mine(r: Result, stat: str):
        return getattr(r, f"{r.side(team_id)}_{stat}")

    def theirs(r: Result, stat: str):
        return getattr(r, f"{'away' if r.side(team_id) == 'home' else 'home'}_{stat}")

    return TeamSummary(
        played=len(games),
        points_per_game=_avg([r.points(team_id) for r in games]),
        goals_for=_avg([r.goals_for(team_id) for r in games]),
        goals_against=_avg([r.goals_against(team_id) for r in games]),
        shots_for=_avg([mine(r, "shots") for r in games]),
        shots_on_target_for=_avg([mine(r, "shots_on_target") for r in games]),
        corners_for=_avg([mine(r, "corners") for r in games]),
        xg_for=_avg([mine(r, "xg") for r in games]),
        xg_against=_avg([theirs(r, "xg") for r in games]),
        clean_sheets=_share([r.goals_against(team_id) == 0 for r in games]),
        over_2_5=_share([r.home_goals + r.away_goals >= 3 for r in games]),
        both_scored=_share([r.home_goals > 0 and r.away_goals > 0 for r in games]),
    )


def head_to_head(results: Iterable[Result], team_a: int, team_b: int, before: datetime, n: int = 5) -> list[Result]:
    """Ultimi n scontri diretti prima di `before`, dal più recente."""
    games = [r for r in results if r.kickoff_at < before and {r.home_id, r.away_id} == {team_a, team_b}]
    return sorted(games, key=lambda r: r.kickoff_at, reverse=True)[:n]


@dataclass
class StandingRow:
    team_id: int
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    form: list[str] = field(default_factory=list)  # ultime 5, dalla più recente

    @property
    def points(self) -> int:
        return 3 * self.won + self.drawn

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


def standings(results: Iterable[Result], before: datetime | None = None) -> list[StandingRow]:
    """Classifica di un girone all'italiana.

    Ordine: punti; a parità, classifica avulsa (punti e differenza reti negli scontri diretti tra le
    squadre a pari punti); poi differenza reti generale; poi gol fatti.
    Non tiene conto di penalizzazioni (arriveranno con i dati della Serie C).
    """
    games = sorted((r for r in results if before is None or r.kickoff_at < before), key=lambda r: r.kickoff_at)
    rows: dict[int, StandingRow] = {}
    for r in games:
        for team in (r.home_id, r.away_id):
            row = rows.setdefault(team, StandingRow(team))
            row.played += 1
            row.goals_for += r.goals_for(team)
            row.goals_against += r.goals_against(team)
            outcome = r.outcome(team)
            row.won += outcome == "V"
            row.drawn += outcome == "N"
            row.lost += outcome == "P"
            row.form = [outcome, *row.form][:5]

    by_points: dict[int, list[StandingRow]] = defaultdict(list)
    for row in rows.values():
        by_points[row.points].append(row)

    ordered: list[StandingRow] = []
    for points in sorted(by_points, reverse=True):
        tied = by_points[points]
        if len(tied) > 1:
            ids = {row.team_id for row in tied}
            mini = {row.team_id: (0, 0) for row in tied}  # (punti, differenza reti) negli scontri diretti
            for r in games:
                if r.home_id in ids and r.away_id in ids:
                    for team in (r.home_id, r.away_id):
                        pts, gd = mini[team]
                        mini[team] = (pts + r.points(team), gd + r.goals_for(team) - r.goals_against(team))
            tied.sort(key=lambda row: (*mini[row.team_id], row.goal_difference, row.goals_for), reverse=True)
        ordered += tied
    return ordered
