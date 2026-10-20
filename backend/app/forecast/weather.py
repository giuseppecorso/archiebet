"""Fattori meteo di una partita (D76), dal meteo ora per ora allo stadio di casa. Funzioni pure."""

import math
from datetime import UTC, datetime, timedelta

from app.adapters.open_meteo import Hourly

COMFORT_TEMPERATURE = 15.0  # °C: la temperatura "estrema" si misura come distanza da qui
WINDOW_HOURS = 2  # una partita dura circa due ore dal calcio d'inizio


def match_weather(hourly: Hourly, kickoff: datetime) -> tuple[float, float, float] | None:
    """(pioggia log(1 + mm nelle 2 ore), vento medio km/h, |T media − 15 °C|) oppure None se manca un dato."""
    start = kickoff.astimezone(UTC).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    hours = [hourly.get(start + timedelta(hours=i)) for i in range(WINDOW_HOURS)]
    if any(h is None or None in h for h in hours):
        return None
    rain = sum(h[0] for h in hours)
    wind = sum(h[1] for h in hours) / WINDOW_HOURS
    temp = sum(h[2] for h in hours) / WINDOW_HOURS
    return math.log1p(rain), wind, abs(temp - COMFORT_TEMPERATURE)
