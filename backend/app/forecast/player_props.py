"""Tiri dei giocatori (D110): tiri attesi in una partita e probabilità di "almeno 1 / 2 tiri", "almeno 1 in porta".

Tiri attesi = tiri al minuto del giocatore nella stagione (ristretti verso la media del suo ruolo) × minuti attesi
(media delle ultime 5 presenze) × forza "tiri concessi" dell'avversario × fattore casa/trasferta. Solo dati di prima.
"""

import math
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.forecast.counts import nb_logpmf

MIN_APPEARANCES = 3
LAST_MINUTES = 5
TEAM_K = 8  # restringimento della forza "tiri concessi" (D109)


@dataclass(frozen=True)
class PlayerGame:
    fixture_id: int
    league: int
    season: int
    kickoff: datetime
    team: int
    opponent: int
    home: bool
    player: int
    name: str
    position: str  # "G" | "D" | "M" | "F"
    minutes: int
    shots: int
    on_target: int


def parse_players(body: dict[str, Any], fixture_id: int, league: int, season: int, kickoff: datetime, home_team: int) -> list[PlayerGame]:
    """Righe dei giocatori da /fixtures/players. API-Football scrive null per zero tiri: si conta 0."""
    teams = [t["team"]["id"] for t in body.get("response", [])]
    out = []
    for t in body.get("response", []):
        team = t["team"]["id"]
        opponent = next((x for x in teams if x != team), None)
        if opponent is None:
            continue
        for p in t.get("players", []):
            st = (p.get("statistics") or [{}])[0]
            games = st.get("games") or {}
            shots = st.get("shots") or {}
            out.append(PlayerGame(fixture_id, league, season, kickoff, team, opponent, team == home_team, p["player"]["id"], p["player"].get("name") or "",
                                  games.get("position") or "?", int(games.get("minutes") or 0), int(shots.get("total") or 0), int(shots.get("on") or 0)))  # fmt: skip
    return out


@dataclass(frozen=True)
class PlayerRow:
    fixture_id: int
    player: int
    name: str
    season: int
    minutes: int
    shots: int
    on_target: int
    mean_shots: float  # modello D110
    mean_on: float
    naive_shots: float  # confronto: media a presenza nella stagione
    naive_on: float


@dataclass
class _Player:
    minutes: int = 0
    shots: int = 0
    on: int = 0
    apps: int = 0
    last: deque = field(default_factory=lambda: deque(maxlen=LAST_MINUTES))


@dataclass
class _Tally:
    total: float = 0.0
    n: int = 0


def build_player_rows(games: Sequence[PlayerGame], m: float) -> list[PlayerRow]:
    """Previsione per ogni presenza (minuti > 0) con almeno 3 presenze prima nella stagione; m = minuti fittizi del ruolo."""
    by_fixture: dict[int, list[PlayerGame]] = defaultdict(list)
    for g in games:
        by_fixture[g.fixture_id].append(g)
    order = sorted(by_fixture, key=lambda f: (by_fixture[f][0].kickoff, f))
    players: dict[tuple[int, int, int], _Player] = defaultdict(_Player)  # (campionato, stagione, giocatore)
    role: dict[tuple[int, int, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])  # tiri, in porta, minuti
    conceded: dict[tuple[int, int, int], _Tally] = defaultdict(_Tally)  # tiri concessi dalla squadra
    league_side: dict[tuple[int, int, bool], _Tally] = defaultdict(_Tally)  # tiri di squadra in casa / fuori
    rows = []
    for fid in order:
        fixture = by_fixture[fid]
        g0 = fixture[0]
        lg = (g0.league, g0.season)
        home_t, away_t = league_side[(*lg, True)], league_side[(*lg, False)]
        if home_t.n and away_t.n:
            avg = (home_t.total / home_t.n + away_t.total / away_t.n) / 2
            venue = {True: home_t.total / home_t.n / avg, False: away_t.total / away_t.n / avg}
        else:
            avg, venue = None, {True: 1.0, False: 1.0}
        for g in fixture:
            if g.minutes <= 0:
                continue
            p = players[(g.league, g.season, g.player)]
            r = role[(g.league, g.season, g.position)]
            if p.apps >= MIN_APPEARANCES and r[2] > 0 and avg:
                c = conceded[(g.league, g.season, g.opponent)]
                opp = (c.total + TEAM_K * avg) / (c.n + TEAM_K) / avg
                exp_min = sum(p.last) / len(p.last)
                rate = (p.shots + m * r[0] / r[2]) / (p.minutes + m)
                rate_on = (p.on + m * r[1] / r[2]) / (p.minutes + m)
                factor = exp_min * opp * venue[g.home]
                rows.append(PlayerRow(fid, g.player, g.name, g.season, g.minutes, g.shots, g.on_target, rate * factor, rate_on * factor,
                                      p.shots / p.apps, p.on / p.apps))  # fmt: skip
        # Aggiornamento dopo la partita: giocatori, ruoli, squadre
        team_shots: dict[int, int] = defaultdict(int)
        for g in fixture:
            team_shots[g.team] += g.shots
            if g.minutes <= 0:
                continue
            p = players[(g.league, g.season, g.player)]
            p.minutes += g.minutes
            p.shots += g.shots
            p.on += g.on_target
            p.apps += 1
            p.last.append(g.minutes)
            r = role[(g.league, g.season, g.position)]
            r[0] += g.shots
            r[1] += g.on_target
            r[2] += g.minutes
        for g in {x.team: x for x in fixture}.values():
            c = conceded[(g.league, g.season, g.opponent)]
            c.total += team_shots[g.team]
            c.n += 1
            s = league_side[(*lg, g.home)]
            s.total += team_shots[g.team]
            s.n += 1
    return rows


def prob_at_least(n: int, mean: float, size: float | None) -> float:
    """Probabilità di almeno n eventi: binomiale negativa (size) o Poisson (size None)."""
    if size is None:
        cdf = sum(math.exp(-mean) * mean**k / math.factorial(k) for k in range(n))
    else:
        cdf = sum(math.exp(nb_logpmf(k, mean, size)) for k in range(n))
    return min(max(1.0 - cdf, 1e-9), 1 - 1e-9)


def row_log_loss(row: PlayerRow, size_shots: float | None, size_on: float | None, naive: bool = False) -> float:
    """Log loss sommata di "almeno 1 tiro", "almeno 2 tiri", "almeno 1 tiro in porta"."""
    ms, mo = (row.naive_shots, row.naive_on) if naive else (row.mean_shots, row.mean_on)
    total = 0.0
    for n, mean, size, y in ((1, ms, size_shots, row.shots), (2, ms, size_shots, row.shots), (1, mo, size_on, row.on_target)):
        p = prob_at_least(n, max(mean, 1e-6), size)
        total -= math.log(p if y >= n else 1 - p)
    return total
