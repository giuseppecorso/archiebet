"""Meteo: scelta della città giusta, lettura dell'archivio ora per ora, fattori della partita, stadi da API-Football."""

import math
from datetime import UTC, datetime

import pytest

from app.adapters.api_football import parse_teams
from app.adapters.open_meteo import best_place, parse_hourly
from app.forecast.weather import match_weather
from app.ingest.venues import city_candidates


def test_best_place_is_the_most_populated():
    body = {"results": [
        {"name": "Milan", "latitude": 42.78, "longitude": 12.6, "population": 42},  # frazione omonima in Umbria
        {"name": "Milano", "latitude": 45.46, "longitude": 9.19, "population": 1371498},
    ]}  # fmt: skip
    place = best_place(body)
    assert (place.latitude, place.longitude) == (45.46, 9.19)
    assert best_place({}) is None


HOURLY = parse_hourly({"hourly": {
    "time": ["2024-03-10T13:00", "2024-03-10T14:00", "2024-03-10T15:00"],
    "precipitation": [0.0, 1.5, 2.5],
    "wind_speed_10m": [10.0, 20.0, 30.0],
    "temperature_2m": [4.0, 5.0, None],
}})  # fmt: skip


def test_match_weather_two_hours_from_kickoff():
    kickoff = datetime(2024, 3, 10, 14, 30, tzinfo=UTC)  # finestra 14:00–15:00 (ore piene in UTC)
    assert HOURLY[datetime(2024, 3, 10, 14)] == (1.5, 20.0, 5.0)
    w = match_weather(HOURLY, datetime(2024, 3, 10, 13, 0, tzinfo=UTC))  # 13:00 e 14:00
    assert w == pytest.approx((math.log1p(1.5), 15.0, abs(4.5 - 15)))
    assert match_weather(HOURLY, kickoff) is None  # alle 15:00 manca la temperatura
    assert match_weather(HOURLY, datetime(2024, 3, 11, 13, 0, tzinfo=UTC)) is None  # giorno fuori dall'archivio


def test_parse_teams_with_venue():
    body = {"response": [{
        "team": {"id": 487, "name": "Lazio", "country": "Italy"},
        "venue": {"name": "Stadio Olimpico", "city": "Roma", "surface": "grass"},
    }]}  # fmt: skip
    [v] = parse_teams(body)
    assert (v.team.id, v.team.name, v.country, v.city, v.surface) == (487, "Lazio", "Italy", "Roma", "grass")


def test_city_candidates():


    assert city_candidates("Nottingham, Nottinghamshire", "GB") == [("Nottingham, Nottinghamshire", "GB"), ("Nottingham", "GB")]
    assert city_candidates("Cava de&apos; Tirreni", "IT")[1] == ("Cava de' Tirreni", "IT")
    assert city_candidates("Monaco", "FR") == [("Monaco", "MC")]  # il Monaco gioca nel principato
    assert city_candidates("Reggio Emilia", "IT") == [("Reggio nell'Emilia", "IT")]
