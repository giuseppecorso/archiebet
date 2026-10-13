"""Previsioni di Archie per le partite in programma, salvate nel database (calcolo per partita, sezione 14.2).

Si ricalcola solo quando serve: risultati nuovi, partite nuove in calendario o modello cambiato.
Le partite già iniziate non si toccano più: resta l'ultima previsione fatta prima del calcio d'inizio.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.forecast.data import MODEL_COUNTRY, Game, load_games
from app.forecast.elo import EloTimeline, run_elo
from app.forecast.markets import markets
from app.forecast.model import MODEL_VERSION, ModelConfig, fit_at
from app.models.football import Competition, Match, MatchStatus
from app.models.forecast import MatchPrediction


def data_version(games: list[Game]) -> str:
    """Impronta dei dati usati: cambia se arriva un risultato nuovo (anche di una partita vecchia)."""
    return f"{len(games)}:{games[-1].kickoff_at:%Y%m%d%H%M}" if games else "0"


def refresh_predictions(db: Session, now: datetime, config: ModelConfig = ModelConfig(), force: bool = False) -> int:
    """Calcola e salva le previsioni delle partite non ancora iniziate. Restituisce quante ne ha aggiornate."""
    upcoming = list(
        db.scalars(
            select(Match)
            .join(Competition, Match.competition_id == Competition.id)
            .where(Competition.country == MODEL_COUNTRY, Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now)
        )
    )
    games = load_games(db)
    if not upcoming or not games:
        return 0
    version = data_version(games)
    existing = {
        p.match_id: p
        for p in db.scalars(select(MatchPrediction).where(MatchPrediction.match_id.in_([m.id for m in upcoming])))
    }
    todo = [
        m
        for m in upcoming
        if force
        or m.id not in existing
        or (existing[m.id].data_version, existing[m.id].model_version) != (version, MODEL_VERSION)
    ]
    if not todo:
        return 0

    timeline = EloTimeline(games, run_elo(games, config.elo))
    tier_of = {t: m.competition.tier for m in todo for t in (m.home_team_id, m.away_team_id)}

    def rating(team: int) -> float:
        r = timeline.rating_at(team, now)
        if r is None:  # squadra mai vista in nessuna partita finita: matricola della sua categoria
            return config.elo.tier_base[tier_of[team]] - config.elo.newcomer_penalty
        return r

    kickoffs = [g.kickoff_at for g in games]
    fit = fit_at(games, kickoffs, now, config, extra_teams=tier_of, rating_at=rating)
    if fit is None:
        return 0
    for m in todo:
        lam, mu = fit.expected_goals(m.home_team_id, m.away_team_id)
        mk = markets(fit.score_matrix(m.home_team_id, m.away_team_id))
        values = {
            "model_version": MODEL_VERSION,
            "data_version": version,
            "computed_at": now,
            "data_until": games[-1].kickoff_at,
            "home_rating": round(rating(m.home_team_id), 1),
            "away_rating": round(rating(m.away_team_id), 1),
            "expected_home_goals": round(lam, 3),
            "expected_away_goals": round(mu, 3),
            "markets": {name: {k: round(v, 5) for k, v in probs.items()} for name, probs in mk.items()},
        }
        row = existing.get(m.id)
        if row is None:
            db.add(MatchPrediction(match_id=m.id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
    db.commit()
    return len(todo)
