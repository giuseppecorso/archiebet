"""API del Laboratorio: studiare campionati e squadre sul passato. Solo numeri, niente pronostici."""

from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.football import CompetitionOut, MatchCard, StandingOut, TeamRef, competition_out, match_cards, to_result
from app.auth.deps import CurrentUser, DbSession
from app.forecast.learning_service import load_learning, twins
from app.forecast.picks import best_probabilities
from app.forecast.radar_service import load_book_odds
from app.ingest.teams import competition_sort_key
from app.models import Competition, Match, MatchPrediction, MatchStatus, Team
from app.stats.league_stats import LeagueSummary, league_summary
from app.stats.team_stats import StandingRow, standings

router = APIRouter(prefix="/api/lab", tags=["laboratorio"])


def season_to_url(season: str) -> str:
    """"2024/25" → "2024-25" (la barra non va bene in un indirizzo)."""
    return season.replace("/", "-")


def season_from_url(value: str) -> str:
    return value.replace("-", "/")


# ---------- Modelli di risposta ----------


class SeasonInfo(BaseModel):
    season: str
    matches: int
    finished: int
    pending: int  # ancora da giocare (in programma o rinviate): se > 0 la stagione è in corso
    cancelled: int  # annullate (es. squadre escluse a stagione in corso)


class CompetitionSeasons(BaseModel):
    competition: CompetitionOut
    seasons: list[SeasonInfo]  # dalla più recente


class SeasonDetail(BaseModel):
    competition: CompetitionOut
    season: str
    matches: int
    finished: int
    pending: int
    cancelled: int
    summary: LeagueSummary
    standings: list[StandingOut]


class SeasonTrend(BaseModel):
    season: str
    summary: LeagueSummary


class TeamListItem(BaseModel):
    id: int
    name: str
    last_season: str | None
    last_competition: str | None


class TeamSeason(BaseModel):
    season: str
    competition: CompetitionOut
    rank: int
    teams: int
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    points: int
    complete: bool  # nessuna partita ancora da giocare (le annullate non contano)


class TeamHistory(BaseModel):
    team: TeamRef
    seasons: list[TeamSeason]  # dalla più recente


# ---------- Utilità ----------


def _finished_results(db: Session, competition_id: int, season: str):
    games = db.scalars(
        select(Match).where(Match.competition_id == competition_id, Match.season == season, Match.status == MatchStatus.FINISHED)
    ).all()
    return games, [to_result(m) for m in games]


def _standings_out(rows: list[StandingRow], names: dict[int, str]) -> list[StandingOut]:
    return [
        StandingOut(
            rank=i + 1,
            team=TeamRef(id=row.team_id, name=names[row.team_id]),
            played=row.played,
            won=row.won,
            drawn=row.drawn,
            lost=row.lost,
            goals_for=row.goals_for,
            goals_against=row.goals_against,
            points=row.points,
            form=row.form,
        )
        for i, row in enumerate(rows)
    ]


PENDING = (MatchStatus.SCHEDULED, MatchStatus.POSTPONED)


def _season_counts(db: Session, competition_id: int | None = None):
    """(campionato, stagione) → (totale, finite, da giocare, annullate)."""
    query = select(
        Match.competition_id,
        Match.season,
        func.count(),
        func.sum(case((Match.status == MatchStatus.FINISHED, 1), else_=0)),
        func.sum(case((Match.status.in_(PENDING), 1), else_=0)),
        func.sum(case((Match.status == MatchStatus.CANCELLED, 1), else_=0)),
    ).group_by(Match.competition_id, Match.season)
    if competition_id is not None:
        query = query.where(Match.competition_id == competition_id)
    return {(c, s): (t, f or 0, p or 0, x or 0) for c, s, t, f, p, x in db.execute(query).all()}


def _competition_or_404(db: Session, code: str) -> Competition:
    competition = db.scalar(select(Competition).where(Competition.code == code))
    if competition is None:
        raise HTTPException(404, "Campionato non trovato")
    return competition


# ---------- Campionati ----------


@router.get("/competitions")
def lab_competitions(_: CurrentUser, db: DbSession) -> list[CompetitionSeasons]:
    by_competition: dict[int, list[SeasonInfo]] = defaultdict(list)
    for (competition_id, season), (total, finished, pending, cancelled) in _season_counts(db).items():
        by_competition[competition_id].append(
            SeasonInfo(season=season, matches=total, finished=finished, pending=pending, cancelled=cancelled)
        )
    out = []
    for c in sorted(db.scalars(select(Competition)), key=competition_sort_key):
        seasons = sorted(by_competition.get(c.id, []), key=lambda s: s.season, reverse=True)
        if seasons:
            out.append(CompetitionSeasons(competition=competition_out(c), seasons=seasons))
    return out


@router.get("/competitions/{code}/seasons/{season}")
def lab_season(code: str, season: str, _: CurrentUser, db: DbSession) -> SeasonDetail:
    competition = _competition_or_404(db, code)
    season = season_from_url(season)
    counts = _season_counts(db, competition.id).get((competition.id, season))
    if counts is None:
        raise HTTPException(404, "Stagione non trovata")
    total, _, pending, cancelled = counts
    games, results = _finished_results(db, competition.id, season)
    names = {m.home_team_id: m.home_team.name for m in games} | {m.away_team_id: m.away_team.name for m in games}
    return SeasonDetail(
        competition=competition_out(competition),
        season=season,
        matches=total,
        finished=len(games),
        pending=pending,
        cancelled=cancelled,
        summary=league_summary(results),
        standings=_standings_out(standings(results), names),
    )


@router.get("/competitions/{code}/trend")
def lab_trend(code: str, _: CurrentUser, db: DbSession) -> list[SeasonTrend]:
    """I numeri del campionato stagione per stagione, dalla più vecchia: per vedere come cambia nel tempo."""
    competition = _competition_or_404(db, code)
    games = db.scalars(select(Match).where(Match.competition_id == competition.id, Match.status == MatchStatus.FINISHED)).all()
    by_season: dict[str, list] = defaultdict(list)
    for m in games:
        by_season[m.season].append(to_result(m))
    return [SeasonTrend(season=s, summary=league_summary(by_season[s])) for s in sorted(by_season)]


# ---------- Squadre ----------


@router.get("/teams")
def lab_teams(_: CurrentUser, db: DbSession, q: str = Query("", max_length=50)) -> list[TeamListItem]:
    """Squadre con l'ultima stagione giocata. Con q filtra per nome (senza distinguere maiuscole)."""
    query = select(Team).order_by(Team.name)
    if q.strip():
        query = query.where(Team.name.ilike(f"%{q.strip()}%"))
    teams = db.scalars(query).all()
    latest: dict[int, tuple[str, str]] = {}
    rows = db.execute(
        select(Match.home_team_id, Match.away_team_id, Match.season, Competition.name).join(Competition).order_by(Match.season)
    ).all()
    for home, away, season, competition in rows:
        latest[home] = latest[away] = (season, competition)
    return [
        TeamListItem(id=t.id, name=t.name, last_season=latest.get(t.id, (None, None))[0], last_competition=latest.get(t.id, (None, None))[1])
        for t in teams
    ]


@router.get("/teams/{team_id}")
def lab_team(team_id: int, _: CurrentUser, db: DbSession) -> TeamHistory:
    """Storia della squadra: per ogni campionato e stagione giocati, posizione e numeri finali."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(404, "Squadra non trovata")
    played_in = db.execute(
        select(Match.competition_id, Match.season)
        .where(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
        .distinct()
    ).all()
    counts = _season_counts(db)
    seasons = []
    for competition_id, season in played_in:
        competition = db.get(Competition, competition_id)
        pending = counts[(competition_id, season)][2]
        _, results = _finished_results(db, competition_id, season)
        table = standings(results)
        for rank, row in enumerate(table, start=1):
            if row.team_id == team_id:
                seasons.append(
                    TeamSeason(
                        season=season,
                        competition=competition_out(competition),
                        rank=rank,
                        teams=len(table),
                        played=row.played,
                        won=row.won,
                        drawn=row.drawn,
                        lost=row.lost,
                        goals_for=row.goals_for,
                        goals_against=row.goals_against,
                        points=row.points,
                        complete=pending == 0,
                    )
                )
    seasons.sort(key=lambda s: (s.season, -s.competition.tier), reverse=True)
    return TeamHistory(team=TeamRef(id=team.id, name=team.name), seasons=seasons)


@router.get("/teams/{team_id}/matches")
def lab_team_matches(team_id: int, season: str, _: CurrentUser, db: DbSession) -> list[MatchCard]:
    """Tutte le partite della squadra in una stagione, in ordine di data."""
    if db.get(Team, team_id) is None:
        raise HTTPException(404, "Squadra non trovata")
    games = db.scalars(
        select(Match)
        .where(Match.season == season_from_url(season), or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
        .order_by(Match.kickoff_at)
    ).all()
    return match_cards(db, list(games), datetime.now(UTC))


# ---------- Cosa impara Archie (Fase 7, D117-D121) ----------


@router.get("/learning")
def learning(_: CurrentUser) -> dict:
    """Risultati delle prove che Archie rifà da solo ogni settimana (strategie, quando giocare, taratura, mappa del valore)."""
    report = load_learning()
    if report is None:
        raise HTTPException(404, "Archie non ha ancora fatto le prove: partono entro due ore dall'avvio")
    return report


@router.get("/review")
def review(_: CurrentUser) -> dict:
    """Pagella settimanale di Archie (D132): settimana per settimana Pronostici e multiple, tarature e panchina."""
    from app.forecast.review_service import load_review

    report = load_review()
    if report is None:
        raise HTTPException(404, "La prima pagella arriva con il lavoro settimanale (entro due ore dall'avvio)")
    return report


class TwinExample(BaseModel):
    match_id: int
    league: str
    day: str
    home: str | None
    away: str | None
    score: str


class TwinsOut(BaseModel):
    source: str  # da dove vengono le probabilità della partita
    probabilities: dict[str, float]
    p_over: float | None
    n: int
    observed: dict[str, float]
    expected: dict[str, float]
    over_observed: float | None
    over_expected: float | None
    avg_goals: float
    top_scores: list[tuple[str, float]]
    examples: list[TwinExample]


@router.get("/twins/{match_id}")
def match_twins(match_id: int, _: CurrentUser, db: DbSession) -> TwinsOut:
    """Partite gemelle (D121): le 100 partite passate con le probabilità d'apertura più simili, e come sono finite."""
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Partita non trovata")
    model = db.scalar(select(MatchPrediction).where(MatchPrediction.match_id == match_id))
    best = best_probabilities(load_book_odds(db, [match_id], closing=False).get(match_id, {}), model.markets if model else None)
    if "1X2" not in best:
        raise HTTPException(422, "Per questa partita mancano le probabilità")
    source, probs = best["1X2"]
    p_over = best["OU2.5"][1]["over"] if "OU2.5" in best else None
    t = twins(probs, p_over)
    if t is None:
        raise HTTPException(404, "Archie non ha ancora preparato le partite gemelle")
    ids = [e["match_id"] for e in t["examples"]]
    names = {m.id: (m.home_team.name, m.away_team.name) for m in db.scalars(select(Match).where(Match.id.in_(ids)))}
    examples = [TwinExample(**e, home=names.get(e["match_id"], (None, None))[0], away=names.get(e["match_id"], (None, None))[1]) for e in t["examples"]]
    return TwinsOut(source=source, probabilities=probs, p_over=p_over, **{k: v for k, v in t.items() if k != "examples"}, examples=examples)
