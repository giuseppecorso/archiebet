"""Fattori D89: riposo e coppe, nuovo allenatore, campo sintetico, distanza, assenze."""

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from app.forecast.factors_d89 import (
    CoachSpell,
    Fixture,
    absence_features,
    coach_features,
    coach_features_from_lineups,
    congestion_features,
    distance_features,
    haversine_km,
    is_new_coach,
    rest_days,
    turf_features,
)

SUN = datetime(2026, 3, 15, 15, tzinfo=UTC)


def test_rest_days_counts_any_competition_and_caps():
    played = [SUN - timedelta(days=10, hours=2), SUN - timedelta(days=3)]
    assert rest_days(SUN, played) == pytest.approx(3.0)
    assert rest_days(SUN, []) == 10.0
    assert rest_days(SUN, [SUN - timedelta(days=30)]) == 10.0


def test_congestion_features():
    f = Fixture(1, SUN, home_id=10, away_id=20)
    all_matches = {10: [SUN - timedelta(days=3)], 20: [SUN - timedelta(days=7)]}
    european = {10: [SUN - timedelta(days=3)], 20: [SUN + timedelta(days=3)]}  # casa ha giocato giovedì, ospite gioca mercoledì
    assert congestion_features([f], all_matches, european) == {1: [pytest.approx(-4.0), 1.0, -1.0]}


def test_new_coach_only_mid_season_and_recent():
    spells = [CoachSpell(date(2025, 7, 1), date(2025, 11, 2)), CoachSpell(date(2025, 11, 3), None)]
    assert is_new_coach(date(2025, 11, 20), spells)  # 17 giorni dopo il cambio
    assert not is_new_coach(date(2026, 1, 20), spells)  # oltre 45 giorni
    assert not is_new_coach(date(2025, 8, 30), spells)  # arrivato d'estate: non è un cambio a stagione in corso
    f = Fixture(1, datetime(2025, 11, 20, 15, tzinfo=UTC), 10, 20)
    assert coach_features([f], {10: spells}) == {1: [1.0]}


def test_coach_change_from_lineups():
    t = [SUN + timedelta(days=7 * k) for k in range(4)]
    fixtures = [Fixture(k, t[k], 10, 20 + k) for k in range(4)]
    coach_of = {(0, 10): 1, (1, 10): 1, (2, 10): 2, (3, 10): 2}  # cambio alla terza partita
    feats = coach_features_from_lineups(fixtures, coach_of)
    assert [feats[k][0] for k in range(4)] == [0.0, 0.0, 1.0, 1.0]


def test_turf_and_distance():
    f = Fixture(1, SUN, 10, 20)
    assert turf_features([f], {10: "artificial turf", 20: "grass"}) == {1: [1.0, 1.0]}
    assert turf_features([f], {10: "grass", 20: "grass"}) == {1: [0.0, 0.0]}
    milano, napoli = (45.4781, 9.1240), (40.8279, 14.1931)
    assert haversine_km(milano, napoli) == pytest.approx(659, abs=5)
    assert distance_features([f], {10: milano, 20: napoli})[1][0] == pytest.approx(math.log1p(haversine_km(milano, napoli)))
    assert distance_features([f], {10: milano}) == {}


def test_absences_against_regular_starters():
    xi = tuple(range(1, 12))
    fixtures = [Fixture(k, SUN + timedelta(days=7 * k), 10, 20) for k in range(4)]
    starters = {(k, team): xi for k in range(3) for team in (10, 20)}
    starters[(3, 10)] = xi[:8] + (90, 91, 92)  # tre titolari abituali fuori
    starters[(3, 20)] = xi
    feats = absence_features(fixtures, starters)
    assert set(feats) == {3}  # servono almeno 3 partite precedenti
    assert feats[3][0] == pytest.approx(3 / 11)
