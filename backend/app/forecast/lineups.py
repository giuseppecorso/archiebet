"""Formazioni previste (Fase 8, D123): chi parte titolare, dalle ultime partite della squadra.

Prova D123: "stessi titolari dell'ultima partita" indovina quanto o più del metodo pesato sulle ultime 5 (Serie A
8,5 su 11 contro 8,3). Quindi la formazione prevista è l'ultima, senza gli assenti delle notizie; i buchi si
riempiono con chi è partito titolare più spesso di recente (quota pesata 5-4-3-2-1, mostrata come informazione).
"""

import math
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.forecast.history_sim import Estimate, clustered_mean
from app.forecast.player_props import PlayerGame

WEIGHTS = (5, 4, 3, 2, 1)  # ultime 5 partite della squadra, la più recente pesa di più
DOUBT = 0.3  # "in dubbio": fuori dall'undici ma titolare almeno nel 30% (pesato) delle ultime partite
MIN_HISTORY = len(WEIGHTS)  # nella prova: solo partite con almeno 5 precedenti della squadra nella stagione
POSITION_ORDER = {"G": 0, "D": 1, "M": 2, "F": 3}


def starters(games: Sequence[PlayerGame]) -> set[int]:
    """Titolari di una squadra in una partita. Se API-Football non segna chi è entrato dalla panchina (succede nella
    stagione in corso: "substitute" sempre falso), titolari = gli 11 con più minuti."""
    played = [g for g in games if g.minutes > 0]
    if any(g.substitute for g in games):
        return {g.player for g in played if not g.substitute}
    return {g.player for g in sorted(played, key=lambda g: -g.minutes)[:11]}


@dataclass(frozen=True)
class Probable:
    player: int
    name: str
    position: str
    p_start: float  # quota pesata di partenze da titolare nelle ultime 5 partite


@dataclass(frozen=True)
class Lineup:
    eleven: list[Probable]
    doubtful: list[Probable]
    based_on: int  # partite usate


def _team_fixtures(games: Sequence[PlayerGame], team: int, before: datetime) -> list[int]:
    """Partite della squadra prima di "before", dalla più recente."""
    return [fid for _, fid in sorted({(g.kickoff, g.fixture_id) for g in games if g.team == team and g.kickoff < before}, reverse=True)]


def recent_starts(games: Sequence[PlayerGame], team: int, before: datetime) -> tuple[list[Probable], list[int]]:
    """Tutti i giocatori delle ultime 5 partite con la quota pesata di partenze da titolare, e le partite usate."""
    recent = _team_fixtures(games, team, before)[: len(WEIGHTS)]
    w = dict(zip(recent, WEIGHTS))
    total = sum(w.values())
    score: dict[int, float] = defaultdict(float)
    info: dict[int, tuple[str, str]] = {}
    by_fixture: dict[int, list[PlayerGame]] = defaultdict(list)
    for g in games:
        if g.team == team and g.fixture_id in w:
            by_fixture[g.fixture_id].append(g)
    for fid in recent:  # dalla più recente: il nome è quello usato per ultimo
        for g in by_fixture[fid]:
            info.setdefault(g.player, (g.name, g.position))
        for pid in starters(by_fixture[fid]):
            score[pid] += w[fid]
    players = [Probable(pid, name, pos, score[pid] / total) for pid, (name, pos) in info.items()]
    return sorted(players, key=lambda p: (-p.p_start, p.name)), recent


def _order(players: Sequence[Probable]) -> list[Probable]:
    return sorted(players, key=lambda p: (POSITION_ORDER.get(p.position, 9), -p.p_start, p.name))


def weighted_lineup(games: Sequence[PlayerGame], team: int, before: datetime, absent: Collection[int] = ()) -> Lineup | None:
    """Metodo pesato (provato in D123): il portiere più probabile + i 10 giocatori di movimento più probabili."""
    ranked, recent = recent_starts(games, team, before)
    if not recent:
        return None
    ranked = [p for p in ranked if p.player not in absent and p.p_start > 0]
    keeper = next((p for p in ranked if p.position == "G"), None)
    eleven = ([keeper] if keeper else []) + [p for p in ranked if p.position != "G"][:10]
    chosen = {p.player for p in eleven}
    doubtful = [p for p in ranked if p.player not in chosen and p.p_start >= DOUBT and p.position != "G"][:4]
    return Lineup(_order(eleven), doubtful, len(recent))


def last_lineup(games: Sequence[PlayerGame], team: int, before: datetime) -> set[int]:
    """Gli stessi titolari dell'ultima partita."""
    recent = _team_fixtures(games, team, before)
    if not recent:
        return set()
    return starters([g for g in games if g.fixture_id == recent[0] and g.team == team])


def predicted_lineup(games: Sequence[PlayerGame], team: int, before: datetime, absent: Collection[int] = ()) -> Lineup | None:
    """Formazione prevista (D123): l'ultima formazione senza gli assenti, completata dai più presenti di recente."""
    ranked, recent = recent_starts(games, team, before)
    if not recent:
        return None
    available = [p for p in ranked if p.player not in absent]
    last = last_lineup(games, team, before)
    eleven = [p for p in available if p.player in last]
    has_keeper = any(p.position == "G" for p in eleven)
    for p in available:  # buchi lasciati dagli assenti: i più presenti di recente, un solo portiere
        if len(eleven) >= 11:
            break
        if p.player in last or p.p_start == 0 or (p.position == "G" and has_keeper):
            continue
        if p.position != "G" and not has_keeper and len(eleven) == 10:
            continue  # l'ultimo posto libero spetta al portiere
        eleven.append(p)
        has_keeper = has_keeper or p.position == "G"
    chosen = {p.player for p in eleven}
    doubtful = [p for p in available if p.player not in chosen and p.p_start >= DOUBT and p.position != "G"][:4]
    return Lineup(_order(eleven), doubtful, len(recent))


@dataclass(frozen=True)
class LineupTest:
    n: int
    archie: float  # titolari indovinati su 11, in media (metodo pesato)
    last: float  # con l'ultima formazione
    gain: Estimate  # pesato meno ultima formazione, appaiato
    passes: bool


def backtest(games: Sequence[PlayerGame]) -> LineupTest | None:
    """D123: titolari indovinati dal metodo pesato contro "stessi titolari dell'ultima partita"."""
    by_team_fixture: dict[tuple[int, int], list[PlayerGame]] = defaultdict(list)
    for g in games:
        by_team_fixture[(g.team, g.fixture_id)].append(g)
    a_hits, l_hits, ids = [], [], []
    for (team, fid), rows in by_team_fixture.items():
        actual = starters(rows)
        kickoff = rows[0].kickoff
        if len(actual) != 11 or len(_team_fixtures(games, team, kickoff)) < MIN_HISTORY:
            continue
        lineup = weighted_lineup(games, team, kickoff)
        last = last_lineup(games, team, kickoff)
        if lineup is None or not last:
            continue
        a_hits.append(len({p.player for p in lineup.eleven} & actual))
        l_hits.append(len(last & actual))
        ids.append(fid * 100_000 + team)
    if len(ids) < 2:
        return None
    gain = clustered_mean([a - b for a, b in zip(a_hits, l_hits)], ids)
    passes = math.isfinite(gain.std_error) and gain.mean > 2 * gain.std_error
    return LineupTest(len(ids), sum(a_hits) / len(ids), sum(l_hits) / len(ids), gain, passes)
