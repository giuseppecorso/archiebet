"""Fattori della prova D89: partite ravvicinate, nuovo allenatore, campo sintetico, distanza, assenze.

Ogni funzione riceve dati già pronti (squadre con i nostri id) e restituisce, per partita, i valori del fattore
come "casa meno ospite" (o per lato, dove serve). Tutto usa solo ciò che si sa prima del calcio d'inizio:
il calendario delle coppe è noto in anticipo, le formazioni escono prima della partita.
"""

import math
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

MAX_REST_DAYS = 10.0
EURO_WINDOW = timedelta(days=4)
NEW_COACH_DAYS = 45
REGULARS_FROM_LAST = 5  # titolari abituali: i più presenti nelle ultime 5 partite di campionato


@dataclass(frozen=True)
class Fixture:
    match_id: int
    kickoff: datetime
    home_id: int
    away_id: int


def _sorted_dates(dates: Mapping[int, Iterable[datetime]]) -> dict[int, list[datetime]]:
    return {team: sorted(set(ds)) for team, ds in dates.items()}


def rest_days(kickoff: datetime, played: Sequence[datetime]) -> float:
    """Giorni dall'ultima partita giocata prima di questa (tutte le competizioni), al massimo 10."""
    i = bisect_left(played, kickoff)
    if i == 0:
        return MAX_REST_DAYS
    return min(MAX_REST_DAYS, (kickoff - played[i - 1]).total_seconds() / 86400)


def _has_between(dates: Sequence[datetime], low: datetime, high: datetime) -> bool:
    i = bisect_left(dates, low)
    return i < len(dates) and dates[i] <= high


def congestion_features(
    fixtures: Iterable[Fixture], all_matches: Mapping[int, Iterable[datetime]], european: Mapping[int, Iterable[datetime]]
) -> dict[int, list[float]]:
    """F1: [riposo casa − ospite, coppa europea nei 4 giorni prima (casa − ospite), nei 4 giorni dopo (casa − ospite)].

    all_matches: per squadra, i calci d'inizio di tutte le partite ufficiali (campionato e coppe); european: solo coppe europee.
    """
    played, euro = _sorted_dates(all_matches), _sorted_dates(european)
    out = {}
    for f in fixtures:
        rest = [rest_days(f.kickoff, played.get(t, [])) for t in (f.home_id, f.away_id)]
        before = [_has_between(euro.get(t, []), f.kickoff - EURO_WINDOW, f.kickoff - timedelta(hours=1)) for t in (f.home_id, f.away_id)]
        after = [_has_between(euro.get(t, []), f.kickoff + timedelta(hours=1), f.kickoff + EURO_WINDOW) for t in (f.home_id, f.away_id)]
        out[f.match_id] = [rest[0] - rest[1], float(before[0]) - float(before[1]), float(after[0]) - float(after[1])]
    return out


@dataclass(frozen=True)
class CoachSpell:
    start: date
    end: date | None


def is_new_coach(day: date, spells: Sequence[CoachSpell]) -> bool:
    """Allenatore arrivato a stagione in corso (non d'estate) da non più di 45 giorni."""
    for s in spells:
        if s.start <= day and (s.end is None or day <= s.end):
            mid_season = not (6 <= s.start.month <= 7 or (s.start.month == 8 and s.start.day <= 15))
            return mid_season and (day - s.start).days <= NEW_COACH_DAYS
    return False


def coach_features(fixtures: Iterable[Fixture], spells: Mapping[int, Sequence[CoachSpell]]) -> dict[int, list[float]]:
    """F2 (date da /coachs): [nuovo allenatore casa − nuovo allenatore ospite]."""
    out = {}
    for f in fixtures:
        day = f.kickoff.date()
        out[f.match_id] = [float(is_new_coach(day, spells.get(f.home_id, ()))) - float(is_new_coach(day, spells.get(f.away_id, ())))]
    return out


@dataclass
class _Bench:
    coach: int
    since: datetime  # prima partita con questo allenatore
    season_start: datetime  # prima partita della stagione della squadra
    last_match: datetime


def coach_features_from_lineups(fixtures: Sequence[Fixture], coach_of: Mapping[tuple[int, int], int]) -> dict[int, list[float]]:
    """F2 in Serie C: l'allenatore della formazione ufficiale. "Nuovo" = cambiato a stagione in corso
    (non alla prima partita della stagione) e in panchina da non più di 45 giorni.

    coach_of[(match_id, team_id)] = id dell'allenatore. Più di 120 giorni senza partite = nuova stagione.
    """
    bench: dict[int, _Bench] = {}
    out = {}
    for f in sorted(fixtures, key=lambda x: x.kickoff):
        flags = []
        for team in (f.home_id, f.away_id):
            coach = coach_of.get((f.match_id, team))
            b = bench.get(team)
            if coach is None:
                flags.append(0.0)
                continue
            if b is None or f.kickoff - b.last_match > timedelta(days=120):
                bench[team] = _Bench(coach, f.kickoff, f.kickoff, f.kickoff)
                flags.append(0.0)
                continue
            if coach != b.coach:
                b.coach, b.since = coach, f.kickoff
            b.last_match = f.kickoff
            flags.append(float(b.since > b.season_start and (f.kickoff - b.since).days <= NEW_COACH_DAYS))
        out[f.match_id] = [flags[0] - flags[1]]
    return out


def is_artificial(surface: str | None) -> bool:
    return bool(surface) and "artificial" in surface.lower()


def turf_features(fixtures: Iterable[Fixture], surface: Mapping[int, str | None]) -> dict[int, list[float]]:
    """F4: [casa sul sintetico, ospite abituato all'erba che gioca sul sintetico]."""
    out = {}
    for f in fixtures:
        home_art = is_artificial(surface.get(f.home_id))
        away_grass = surface.get(f.away_id) is not None and not is_artificial(surface.get(f.away_id))
        out[f.match_id] = [float(home_art), float(home_art and away_grass)]
    return out


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def distance_features(fixtures: Iterable[Fixture], coords: Mapping[int, tuple[float, float]]) -> dict[int, list[float]]:
    """F5: [log(1 + km) tra lo stadio di casa e quello dell'ospite]; solo dove ci sono le coordinate di entrambi."""
    out = {}
    for f in fixtures:
        if f.home_id in coords and f.away_id in coords:
            out[f.match_id] = [math.log1p(haversine_km(coords[f.home_id], coords[f.away_id]))]
    return out


def absence_features(fixtures: Sequence[Fixture], starters: Mapping[tuple[int, int], Sequence[int]]) -> dict[int, list[float]]:
    """F1b: [quota dei titolari abituali assenti dalla formazione, casa − ospite].

    Titolari abituali = gli 11 giocatori più presenti dall'inizio nelle 5 partite precedenti della squadra.
    Solo partite in cui entrambe le squadre hanno la formazione e almeno 3 partite precedenti.
    """
    history: dict[int, list[tuple[int, ...]]] = defaultdict(list)
    out = {}
    for f in sorted(fixtures, key=lambda x: x.kickoff):
        today = {t: starters.get((f.match_id, t)) for t in (f.home_id, f.away_id)}
        shares = []
        for team in (f.home_id, f.away_id):
            past = history[team][-REGULARS_FROM_LAST:]
            if not today[team] or len(past) < 3:
                shares = None
                break
            counts: dict[int, int] = defaultdict(int)
            for xi in past:
                for p in xi:
                    counts[p] += 1
            regulars = set(sorted(counts, key=lambda p: (-counts[p], p))[:11])
            shares.append(len(regulars - set(today[team])) / len(regulars))
        if shares is not None:
            out[f.match_id] = [shares[0] - shares[1]]
        for team in (f.home_id, f.away_id):
            if today[team]:
                history[team].append(tuple(today[team]))
    return out
