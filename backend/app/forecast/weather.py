"""Fattori meteo di una partita (D76), dal meteo ora per ora allo stadio di casa. Funzioni pure."""

import math
from datetime import UTC, datetime, timedelta

from app.adapters.open_meteo import Hourly

COMFORT_TEMPERATURE = 15.0  # °C: la temperatura "estrema" si misura come distanza da qui
WINDOW_HOURS = 2  # una partita dura circa due ore dal calcio d'inizio


def raw_weather(hourly: Hourly, kickoff: datetime) -> tuple[float, float, float] | None:
    """(pioggia mm nelle 2 ore, vento medio km/h, temperatura media °C) oppure None se manca un dato."""
    start = kickoff.astimezone(UTC).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    hours = [hourly.get(start + timedelta(hours=i)) for i in range(WINDOW_HOURS)]
    if any(h is None or None in h for h in hours):
        return None
    rain = sum(h[0] for h in hours)
    return rain, sum(h[1] for h in hours) / WINDOW_HOURS, sum(h[2] for h in hours) / WINDOW_HOURS


def weather_factors(raw: tuple[float, float, float]) -> tuple[float, float, float]:
    """I fattori di D76: (pioggia log(1 + mm), vento km/h, |T − 15 °C|)."""
    rain, wind, temp = raw
    return math.log1p(rain), wind, abs(temp - COMFORT_TEMPERATURE)


def match_weather(hourly: Hourly, kickoff: datetime) -> tuple[float, float, float] | None:
    raw = raw_weather(hourly, kickoff)
    return weather_factors(raw) if raw else None


def monthly_normals(daily: dict[str, float | None]) -> dict[int, float]:
    """Temperatura media di ogni mese ("normale climatica") da temperature giornaliere {"2017-01-03": 4.2, ...}."""
    by_month: dict[int, list[float]] = {}
    for day, t in daily.items():
        if t is not None:
            by_month.setdefault(int(day[5:7]), []).append(t)
    return {m: sum(v) / len(v) for m, v in by_month.items()}


def climate_shock(match_temperature: float, away_normals: dict[int, float], month: int) -> tuple[float, float] | None:
    """Shock climatico dell'ospite (D78): (T partita − normale del mese a casa sua, e il suo valore assoluto)."""
    if month not in away_normals:
        return None
    d = match_temperature - away_normals[month]
    return d, abs(d)
