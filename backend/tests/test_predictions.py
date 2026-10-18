"""Previsioni salvate per partita: calcolo, ricalcolo solo se servono, niente ritocchi dopo il calcio d'inizio."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.adapters.football_data import parse_csv
from app.forecast.data import load_games
from app.forecast.demargin import shin
from app.forecast.model import MODEL_VERSION
from app.forecast.service import refresh_predictions
from app.ingest.football_data import import_matches
from app.models import Match, MatchPrediction, Team
from tests.test_football_api import HEADER, day, match_id, seeded  # noqa: F401 (fixture condivisa)


def test_predicts_only_matches_not_yet_started(seeded, db):  # noqa: F811
    assert refresh_predictions(db, datetime.now(UTC)) == 2  # Milan-Inter e Palermo-Bari; Lazio-Milan è già iniziata
    p = db.scalar(select(MatchPrediction).where(MatchPrediction.match_id == match_id(db, "Milan", "Inter")))
    assert p.model_version == MODEL_VERSION
    assert sum(p.markets["1X2"].values()) == pytest.approx(1.0, abs=1e-4)
    assert p.markets["DC"]["1X"] == pytest.approx(p.markets["1X2"]["1"] + p.markets["1X2"]["X"], abs=1e-4)
    assert p.expected_home_goals > 0 and p.expected_away_goals > 0
    # Inter ha vinto più di Milan nelle giornate giocate: rating più alto
    assert p.away_rating > p.home_rating
    assert db.scalar(select(MatchPrediction).where(MatchPrediction.match_id == match_id(db, "Lazio", "Milan"))) is None


def test_newcomer_without_history_gets_a_prediction(seeded, db):  # noqa: F811
    refresh_predictions(db, datetime.now(UTC))
    p = db.scalar(select(MatchPrediction).where(MatchPrediction.match_id == match_id(db, "Palermo", "Bari")))
    assert p.home_rating == pytest.approx(1350 - 50)  # Serie B mai vista: valore base meno malus matricola


def test_recomputes_only_when_data_change(seeded, db):  # noqa: F811
    now = datetime.now(UTC)
    assert refresh_predictions(db, now) == 2
    assert refresh_predictions(db, now) == 0  # niente di nuovo
    late = db.get(Match, match_id(db, "Lazio", "Milan"))
    late.home_goals, late.away_goals, late.status = 0, 2, "finished"  # arriva il risultato mancante
    db.commit()
    assert refresh_predictions(db, now) == 2
    assert refresh_predictions(db, now, force=True) == 2


def test_started_matches_keep_their_last_prediction(seeded, db):  # noqa: F811
    now = datetime.now(UTC)
    refresh_predictions(db, now)
    target = match_id(db, "Milan", "Inter")
    before = db.scalar(select(MatchPrediction).where(MatchPrediction.match_id == target)).computed_at
    later = now + timedelta(days=5)  # la partita è già iniziata
    refresh_predictions(db, later, force=True)
    after = db.scalar(select(MatchPrediction).where(MatchPrediction.match_id == target)).computed_at
    assert after == before


def test_match_detail_shows_prediction_and_market(logged_client, seeded, db):  # noqa: F811
    target = match_id(db, "Milan", "Inter")
    assert logged_client.get(f"/api/matches/{target}").json()["prediction"] is None  # non ancora calcolata
    refresh_predictions(db, datetime.now(UTC))
    pred = logged_client.get(f"/api/matches/{target}").json()["prediction"]
    assert "trial" not in pred  # modello uscito dalla prova (D59)
    assert pred["model_version"] == MODEL_VERSION
    assert set(pred["markets"]) >= {"1X2", "DC", "OU2.5", "GG"}
    # Mercato: quote medie di apertura 3,1 / 3,4 / 2,3 senza margine (Shin, D72)
    fair = shin([3.1, 3.4, 2.3])
    ref = pred["market"]["1X2"]
    assert ref["source"] == "Media mercato · apertura"
    assert ref["probabilities"]["1"] == pytest.approx(fair[0])


def test_foreign_leagues_stay_out_of_the_italian_model(seeded, db):  # noqa: F811
    italian = len(load_games(db))
    rows = HEADER + f"E0,{day(-7)},15:00,Arsenal,Chelsea,2,1,12,9,2.0,3.4,3.8,2.1,3.4,3.6\n"
    import_matches(db, parse_csv(rows), season="2026/27")
    import_matches(db, parse_csv(f"Div,Date,Time,HomeTeam,AwayTeam,AvgH,AvgD,AvgA\nE0,{day(3)},15:00,Chelsea,Arsenal,2.5,3.3,2.9\n"), season="2026/27")
    assert db.scalar(select(Team.country).where(Team.name == "Arsenal")) == "Inghilterra"
    assert len(load_games(db)) == italian  # Arsenal-Chelsea non entra nel modello italiano
    assert len(load_games(db, "Inghilterra")) == 1
    assert refresh_predictions(db, datetime.now(UTC)) == 2  # solo Milan-Inter e Palermo-Bari, non Chelsea-Arsenal
