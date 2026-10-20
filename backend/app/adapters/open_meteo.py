"""Fonte dati Open-Meteo: coordinate delle città e meteo storico ora per ora (D76). Gratuito per uso non commerciale.

Verificato sulle risposte reali (ottobre 2026):
- geocoding: geocoding-api.open-meteo.com/v1/search?name=&count=&countryCode= → results[] con latitude, longitude,
  population; il primo risultato può essere un paesino omonimo ("Milano" → frazione di 42 abitanti): si sceglie
  il più popoloso
- archivio: archive-api.open-meteo.com/v1/archive con hourly=precipitation,wind_speed_10m,temperature_2m e
  timezone=UTC → hourly.time ("2019-07-01T00:00") e una lista per variabile (mm, km/h, °C); 6 anni in una richiesta
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.adapters.base import DataSourceAdapter
from app.adapters.cache import FileCache

SOURCE = "open-meteo"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY = ("precipitation", "wind_speed_10m", "temperature_2m")
PAUSE_SECONDS = 0.3  # cortesia verso un servizio gratuito


class OpenMeteoError(Exception):
    """Errore restituito dal servizio. Non viene mai salvato in cache."""


@dataclass(frozen=True)
class Place:
    latitude: float
    longitude: float
    population: int


def best_place(body: dict[str, Any]) -> Place | None:
    """Il risultato più popoloso (evita i paesini omonimi)."""
    results = body.get("results") or []
    if not results:
        return None
    best = max(results, key=lambda r: r.get("population") or 0)
    return Place(float(best["latitude"]), float(best["longitude"]), int(best.get("population") or 0))


Hourly = dict[datetime, tuple[float | None, float | None, float | None]]  # ora UTC → (pioggia mm, vento km/h, °C)


def parse_hourly(body: dict[str, Any]) -> Hourly:
    h = body.get("hourly") or {}
    columns = [h.get(name) or [] for name in HOURLY]
    return {datetime.fromisoformat(t): tuple(col[i] if i < len(col) else None for col in columns) for i, t in enumerate(h.get("time") or [])}


class OpenMeteoAdapter(DataSourceAdapter):
    source = SOURCE

    def __init__(
        self,
        cache: FileCache,
        on_call: Callable[[str], None] | None = None,
        http_get: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        super().__init__(cache, on_call)
        self._http_get = http_get or _http_get
        self._sleep = sleep

    def _request(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        self._sleep(PAUSE_SECONDS)
        status, body = self._http_get(url, params)
        if status != 200 or (isinstance(body, dict) and body.get("error")):
            raise OpenMeteoError(f"HTTP {status} da {url}: {body.get('reason', '') if isinstance(body, dict) else ''}")
        return body

    def place(self, city: str, country_code: str) -> Place | None:
        params = {"name": city, "count": 10, "countryCode": country_code, "language": "it"}
        body = self.cached(f"geocoding?name={city}&country={country_code}", timedelta(days=365), lambda: self._request(GEOCODING_URL, params))
        return best_place(body)

    def daily_temperature(self, latitude: float, longitude: float, start: date, end: date) -> dict[str, float | None]:
        """Temperatura media giornaliera (°C) per costruire la normale climatica di una città (D78)."""
        lat, lon = round(latitude, 2), round(longitude, 2)
        params = {"latitude": lat, "longitude": lon, "start_date": start.isoformat(), "end_date": end.isoformat(),
                  "daily": "temperature_2m_mean", "timezone": "UTC"}  # fmt: skip
        body = self.cached(f"daily?lat={lat}&lon={lon}&start={start}&end={end}", timedelta(days=3650), lambda: self._request(ARCHIVE_URL, params))
        d = body.get("daily") or {}
        return dict(zip(d.get("time") or [], d.get("temperature_2m_mean") or []))

    def hourly_uncached(self, latitude: float, longitude: float, start: date, end: date) -> Hourly:
        """Come hourly, ma senza salvare la risposta grezza (anni di dati orari pesano centinaia di MB)."""
        params = {"latitude": round(latitude, 2), "longitude": round(longitude, 2), "start_date": start.isoformat(),
                  "end_date": end.isoformat(), "hourly": ",".join(HOURLY), "timezone": "UTC"}  # fmt: skip
        body = self._request(ARCHIVE_URL, params)
        if self._on_call:
            self._on_call(self.source)
        return parse_hourly(body)

    def hourly(self, latitude: float, longitude: float, start: date, end: date) -> Hourly:
        lat, lon = round(latitude, 2), round(longitude, 2)
        params = {"latitude": lat, "longitude": lon, "start_date": start.isoformat(), "end_date": end.isoformat(),
                  "hourly": ",".join(HOURLY), "timezone": "UTC"}  # fmt: skip
        key = f"archive?lat={lat}&lon={lon}&start={start}&end={end}"
        return parse_hourly(self.cached(key, timedelta(days=3650), lambda: self._request(ARCHIVE_URL, params)))


def _http_get(url: str, params: dict[str, Any]) -> tuple[int, Any]:
    import httpx2

    response = httpx2.get(url, params=params, timeout=120)
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {}
