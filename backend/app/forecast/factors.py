"""Fattori della partita calcolati dai dati che abbiamo, sempre con ciò che si sapeva PRIMA del calcio d'inizio.

Ogni fattore restituisce, per partita, un valore "casa − fuori" (positivo = vantaggio alla squadra di casa).
Entrano nelle previsioni solo se superano la prova del nove contro il mercato (D53).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from app.forecast.data import Game

MAX_REST_DAYS = 8  # oltre una settimana il riposo in più non conta: si taglia qui


def rest_difference(games: Sequence[Game]) -> dict[int, float]:
    """Giorni di riposo (casa − fuori) dall'ultima partita di campionato, tagliati a MAX_REST_DAYS.

    Limite: nei dati non ci sono coppe ed Europa, quindi il riposo vero può essere più corto.
    """
    last: dict[int, Game] = {}
    out: dict[int, float] = {}
    for g in games:
        rests = []
        for team in (g.home_id, g.away_id):
            prev = last.get(team)
            days = MAX_REST_DAYS if prev is None else (g.kickoff_at - prev.kickoff_at).total_seconds() / 86400
            rests.append(min(days, MAX_REST_DAYS))
        out[g.match_id] = rests[0] - rests[1]
        last[g.home_id] = last[g.away_id] = g
    return out


@dataclass(frozen=True)
class SeasonRules:
    """Zone della classifica che contano per la motivazione."""

    relegation: int  # ultimi N posti = retrocessione (o playout)
    target: int  # primi N posti = obiettivo (Europa / playoff)


RULES = {1: SeasonRules(relegation=3, target=7), 2: SeasonRules(relegation=4, target=8)}


def nothing_to_play_for(games: Sequence[Game]) -> dict[int, float]:
    """Squadre già salve che non possono più arrivare all'obiettivo (casa − fuori: −1, 0 o +1).

    Calcolo prudente con la classifica prima del calcio d'inizio: "salva" se ha più punti di quanti ne
    possa fare la prima squadra in zona retrocessione; "senza obiettivo" se anche vincendo tutte non
    raggiunge i punti attuali della squadra all'ultimo posto utile. Pari punti ignorati.
    """
    by_season: dict[tuple[int, str], list[Game]] = defaultdict(list)
    for g in games:
        by_season[(g.competition_id, g.season)].append(g)

    out: dict[int, float] = {}
    for season_games in by_season.values():
        rules = RULES.get(season_games[0].tier)
        teams = {t for g in season_games for t in (g.home_id, g.away_id)}
        total = 2 * (len(teams) - 1)  # partite a testa: il calendario è noto da inizio stagione
        points = dict.fromkeys(teams, 0)
        played = dict.fromkeys(teams, 0)
        i = 0
        while i < len(season_games):
            # Partite con lo stesso calcio d'inizio: tutte con la classifica di prima
            j = i
            while j < len(season_games) and season_games[j].kickoff_at == season_games[i].kickoff_at:
                j += 1
            table = sorted(teams, key=lambda t: points[t], reverse=True)
            for g in season_games[i:j]:
                if rules is None:
                    out[g.match_id] = 0.0
                    continue
                flags = []
                for team in (g.home_id, g.away_id):
                    first_down = table[len(table) - rules.relegation]
                    safe = points[team] > points[first_down] + 3 * (total - played[first_down]) and team != first_down
                    last_target = table[rules.target - 1]
                    out_of_reach = points[team] + 3 * (total - played[team]) < points[last_target]
                    flags.append(1.0 if safe and out_of_reach else 0.0)
                out[g.match_id] = flags[0] - flags[1]
            for g in season_games[i:j]:
                hp, ap = (3, 0) if g.home_goals > g.away_goals else (1, 1) if g.home_goals == g.away_goals else (0, 3)
                points[g.home_id] += hp
                points[g.away_id] += ap
                played[g.home_id] += 1
                played[g.away_id] += 1
            i = j
    return out
