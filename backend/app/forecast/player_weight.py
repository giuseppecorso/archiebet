"""Peso dei giocatori (D156): chi gioca oggi rispetto all'undici abituale, in attacco e in qualità. Funzioni pure.

Per ogni giocatore, nelle partite dei 365 giorni precedenti (mai dati dal futuro):
- attacco = tiri + passaggi chiave ogni 90 minuti;
- qualità = voto medio di API-Football, pesato per i minuti.
Entrambi sono avvicinati alla media del ruolo come se il giocatore avesse 5 partite medie in più: chi ha giocato poco
vale quasi la media, chi ha giocato tanto vale quello che ha fatto.

Undici abituale = gli 11 con più minuti nelle ultime 10 partite della squadra. Confronto con i titolari di oggi:
- A = log(attacco dei titolari / attacco dell'undici abituale): se manca chi tira e gioca chi tira meno, A < 0;
- R = voto medio dei titolari − voto medio dell'undici abituale.
Il sostituto entra col suo peso: per questo si confrontano due undici e non si contano solo gli assenti.
"""

import math
from bisect import bisect_left
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

SHRINK_GAMES = 5.0  # la media del ruolo pesa come 5 partite intere
WINDOW_DAYS = 365
USUAL_GAMES = 10  # partite che definiscono l'undici abituale
MIN_TEAM_GAMES = 5  # meno di così l'undici abituale non si sa
MIN_RATED_MINUTES = 15  # API-Football non dà il voto a chi gioca pochi minuti
POSITIONS = ("G", "D", "M", "F")


@dataclass(frozen=True)
class Appearance:
    """Un giocatore in una partita (anche in panchina senza entrare: minuti 0)."""

    fixture_id: int
    date: datetime
    team: int
    player: int
    name: str
    position: str
    minutes: int
    started: bool
    shots: int
    key_passes: int
    rating: float | None


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_appearances(body: dict[str, Any], fixture_id: int, date: datetime) -> list[Appearance]:
    """Righe di /fixtures/players. Titolare = non "substitute" con minuti; se API-Football non lo segna (succede nella
    stagione in corso, D123) i titolari sono gli 11 con più minuti."""
    out = []
    for block in body.get("response", []):
        team = block["team"]["id"]
        rows = []
        for p in block.get("players", []):
            s = (p.get("statistics") or [{}])[0]
            games, shots, passes = s.get("games") or {}, s.get("shots") or {}, s.get("passes") or {}
            minutes = int(_num(games.get("minutes")))
            rating = _num(games.get("rating")) if games.get("rating") and minutes >= MIN_RATED_MINUTES else None
            rows.append([p["player"]["id"], p["player"].get("name") or "", games.get("position") or "M", minutes,
                         minutes > 0 and not games.get("substitute"), int(_num(shots.get("total"))), int(_num(passes.get("key"))), rating])  # fmt: skip
        if sum(r[4] for r in rows) != 11:
            starters = {r[0] for r in sorted(rows, key=lambda r: r[3], reverse=True)[:11] if r[3] > 0}
            for r in rows:
                r[4] = r[0] in starters
        out += [Appearance(fixture_id, date, team, *r) for r in rows]
    return out


@dataclass(frozen=True)
class RoleMeans:
    """Media del ruolo: attacco ogni 90 minuti e voto."""

    attack: dict[str, float]
    rating: dict[str, float]


def role_means(apps: Iterable[Appearance]) -> RoleMeans:
    att, mins, rat, rated = defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(float)
    for a in apps:
        if a.minutes <= 0:
            continue
        att[a.position] += a.shots + a.key_passes
        mins[a.position] += a.minutes / 90
        if a.rating is not None:
            rat[a.position] += a.rating * a.minutes / 90
            rated[a.position] += a.minutes / 90
    all_att = sum(att.values()) / max(sum(mins.values()), 1e-9)
    all_rat = sum(rat.values()) / sum(rated.values()) if sum(rated.values()) else 6.7
    return RoleMeans({p: att[p] / mins[p] if mins[p] else all_att for p in POSITIONS},
                     {p: rat[p] / rated[p] if rated[p] else all_rat for p in POSITIONS})  # fmt: skip


@dataclass
class _Player:
    dates: list = field(default_factory=list)
    # somme cumulate: [90 minuti, tiri + passaggi chiave, voto × 90 minuti, 90 minuti con voto]
    sums: list = field(default_factory=lambda: [(0.0, 0.0, 0.0, 0.0)])
    positions: list = field(default_factory=list)
    name: str = ""


@dataclass(frozen=True)
class Weighted:
    player: int
    name: str
    attack: float  # tiri + passaggi chiave ogni 90 minuti (avvicinati alla media del ruolo)
    rating: float


@dataclass(frozen=True)
class LineupChange:
    attack: float  # A
    quality: float  # R
    missing: tuple[Weighted, ...]  # dell'undici abituale, oggi non titolari
    replacing: tuple[Weighted, ...]  # titolari di oggi fuori dall'undici abituale


class PlayerBook:
    """Le presenze di tutte le partite, indicizzate per giocatore e per squadra."""

    def __init__(self, apps: Iterable[Appearance]):
        rows = sorted(apps, key=lambda a: a.date)
        self.players: dict[int, _Player] = defaultdict(_Player)
        self.team_games: dict[int, list[tuple[datetime, int]]] = defaultdict(list)
        self.by_fixture: dict[tuple[int, int], list[Appearance]] = defaultdict(list)
        for a in rows:
            p = self.players[a.player]
            p.name = a.name or p.name
            p.dates.append(a.date)
            m = a.minutes / 90
            rated = m if a.rating is not None else 0.0
            last = p.sums[-1]
            p.sums.append((last[0] + m, last[1] + a.shots + a.key_passes, last[2] + (a.rating or 0.0) * rated, last[3] + rated))
            p.positions.append(a.position if a.minutes > 0 else None)
            key = (a.team, a.fixture_id)
            if key not in self.by_fixture:
                self.team_games[a.team].append((a.date, a.fixture_id))
            self.by_fixture[key].append(a)

    def weighted(self, player: int, before: datetime, means: RoleMeans, position: str | None = None) -> Weighted:
        """Attacco e voto del giocatore nei 365 giorni prima di `before`, avvicinati alla media del ruolo."""
        p = self.players.get(player) or _Player()
        hi = bisect_left(p.dates, before)
        lo = bisect_left(p.dates, before - timedelta(days=WINDOW_DAYS))
        s_hi, s_lo = p.sums[hi], p.sums[lo]
        m90, att, rat, rated = (s_hi[i] - s_lo[i] for i in range(4))
        seen = [x for x in p.positions[lo:hi] if x]
        role = Counter(seen).most_common(1)[0][0] if seen else (position or "M")
        role = role if role in POSITIONS else "M"
        k = SHRINK_GAMES
        return Weighted(player, p.name, (att + k * means.attack[role]) / (m90 + k), (rat + k * means.rating[role]) / (rated + k))

    def usual_eleven(self, team: int, before: datetime) -> list[int] | None:
        """Gli 11 con più minuti nelle ultime 10 partite della squadra prima di `before` (None se sono meno di 5)."""
        games = self.team_games.get(team, [])
        prev = games[max(0, bisect_left(games, (before, -1)) - USUAL_GAMES) : bisect_left(games, (before, -1))]
        if len(prev) < MIN_TEAM_GAMES:
            return None
        minutes: Counter = Counter()
        for _, fid in prev:
            for a in self.by_fixture[(team, fid)]:
                minutes[a.player] += a.minutes
        return [p for p, _ in minutes.most_common(11)]

    def starters(self, team: int, fixture_id: int) -> list[Appearance]:
        return [a for a in self.by_fixture.get((team, fixture_id), []) if a.started]


def lineup_change(book: PlayerBook, team: int, starters: Sequence[tuple[int, str | None]], kickoff: datetime, means: RoleMeans) -> LineupChange | None:
    """Confronto tra i titolari di oggi (giocatore, ruolo) e l'undici abituale della squadra. None se non si può dire."""
    usual = book.usual_eleven(team, kickoff)
    if usual is None or len(starters) < 11:
        return None
    today = [book.weighted(p, kickoff, means, pos) for p, pos in starters]
    regular = [book.weighted(p, kickoff, means) for p in usual]
    att_today, att_usual = sum(w.attack for w in today), sum(w.attack for w in regular)
    if att_today <= 0 or att_usual <= 0:
        return None
    ids_today = {p for p, _ in starters}
    quality = sum(w.rating for w in today) / len(today) - sum(w.rating for w in regular) / len(regular)
    return LineupChange(
        math.log(att_today / att_usual), quality,
        tuple(sorted((w for w in regular if w.player not in ids_today), key=lambda w: -w.attack)),
        tuple(sorted((w for w in today if w.player not in set(usual)), key=lambda w: -w.attack)),
    )  # fmt: skip


def goals_factor(attack: float, own_quality: float, opponent_quality: float, a: float, b: float, c: float) -> float:
    """Fattore sui gol attesi di una squadra: exp(a·A + b·R_propria − c·R_avversaria)."""
    return math.exp(a * attack + b * own_quality - c * opponent_quality)
