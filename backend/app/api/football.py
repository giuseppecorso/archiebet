"""API di campionati e partite (dati per partita, letti da tutti gli utenti)."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, DbSession
from app.forecast.data import fair_probabilities
from app.ingest.teams import competition_sort_key
from app.models import Competition, Match, MatchOdds, MatchPrediction, MatchStatus
from app.stats.team_stats import Result, TeamSummary, form, head_to_head, standings, summary

router = APIRouter(prefix="/api", tags=["football"])

# Una partita "in programma" ma iniziata da più di così senza risultato è "in attesa del risultato"
RESULT_GRACE = timedelta(hours=2)
BOOKMAKER_LABELS = {
    "market_avg": "Media mercato",
    "market_max": "Migliore mercato",
    "pinnacle": "Pinnacle",
    "bet365": "bet365",
    "betfair_ex": "Betfair Exchange",
    "sisal": "Sisal",
    "snai": "Snai",
    "eurobet": "Eurobet",
    "goldbet": "Goldbet",
    "lottomatica": "Lottomatica",
    "betflag": "BetFlag",
    "bet365_it": "bet365.it",
    "planetwin365": "Planetwin365",
    "betsson": "Betsson",
}


# ---------- Modelli di risposta ----------


class TeamRef(BaseModel):
    id: int
    name: str


class CompetitionOut(BaseModel):
    code: str
    name: str
    country: str
    tier: int


class MatchCard(BaseModel):
    id: int
    competition: CompetitionOut
    season: str
    kickoff_at: datetime
    kickoff_has_time: bool
    status: Literal["scheduled", "finished", "awaiting_result"]
    home: TeamRef
    away: TeamRef
    home_goals: int | None
    away_goals: int | None
    odds_1x2: dict[str, float] | None  # media di mercato: apertura per le prossime, chiusura per le giocate


class CompetitionGroup(BaseModel):
    competition: CompetitionOut
    matches: list[MatchCard]


class FormEntry(BaseModel):
    outcome: str  # V / N / P
    match_id: int
    kickoff_at: datetime
    opponent: str
    venue: Literal["C", "T"]  # in casa / in trasferta
    score: str  # dal punto di vista della squadra, es. "2-1"


class StandingOut(BaseModel):
    rank: int
    team: TeamRef
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    points: int
    form: list[str]


class OddsRow(BaseModel):
    bookmaker: str
    label: str
    market: str
    opening: dict[str, float]
    closing: dict[str, float]


class SideStats(BaseModel):
    team: TeamRef
    form: list[FormEntry]
    season: TeamSummary  # stagione in corso nel campionato
    venue: TeamSummary  # stagione in corso, solo in casa (o solo in trasferta)


class MarketReference(BaseModel):
    source: str  # es. "Pinnacle · chiusura"
    probabilities: dict[str, float]  # senza margine


class PredictionOut(BaseModel):
    model_version: str
    computed_at: datetime
    data_until: datetime  # ultimo risultato usato dal modello
    ratings: list[float]  # Elo [casa, trasferta]
    expected_goals: list[float]  # [casa, trasferta]
    markets: dict[str, dict[str, float]]  # mercato → esito → probabilità di Archie
    market: dict[str, MarketReference]  # stessa cosa secondo il mercato, per confronto


class MatchDetail(BaseModel):
    match: MatchCard
    stats_as_of: datetime  # tutte le statistiche usano solo partite giocate prima di questo istante
    missing_results: int  # partite di campionato già giocate ma senza risultato nei nostri dati: statistiche incomplete
    home: SideStats
    away: SideStats
    head_to_head: list[MatchCard]
    standings: list[StandingOut]
    odds: list[OddsRow]
    match_stats: dict[str, list[int | float | None]] | None  # [casa, trasferta], solo a partita giocata
    prediction: PredictionOut | None = None  # previsione di Archie fatta prima del calcio d'inizio


# ---------- Conversioni ----------


def competition_out(c: Competition) -> CompetitionOut:
    return CompetitionOut(code=c.code, name=c.name, country=c.country, tier=c.tier)


def _status(m: Match, now: datetime) -> str:
    if m.status == MatchStatus.FINISHED:
        return "finished"
    return "awaiting_result" if m.kickoff_at < now - RESULT_GRACE else "scheduled"


def _odds_1x2(db: Session, matches: list[Match]) -> dict[int, dict[str, float]]:
    """Quota media di mercato 1X2: chiusura se la partita è finita (e c'è), altrimenti apertura."""
    if not matches:
        return {}
    rows = db.execute(
        select(MatchOdds.match_id, MatchOdds.selection, MatchOdds.price, MatchOdds.is_closing).where(
            MatchOdds.match_id.in_([m.id for m in matches]),
            MatchOdds.bookmaker == "market_avg",
            MatchOdds.market == "1X2",
        )
    ).all()
    by_kind: dict[tuple[int, bool], dict[str, float]] = defaultdict(dict)
    for match_id, selection, price, closing in rows:
        by_kind[(match_id, closing)][selection] = float(price)
    result = {}
    for m in matches:
        prefer = [True, False] if m.status == MatchStatus.FINISHED else [False, True]
        for closing in prefer:
            if len(by_kind.get((m.id, closing), {})) == 3:
                result[m.id] = by_kind[(m.id, closing)]
                break
    return result


def match_cards(db: Session, matches: list[Match], now: datetime) -> list[MatchCard]:
    odds = _odds_1x2(db, matches)
    return [
        MatchCard(
            id=m.id,
            competition=competition_out(m.competition),
            season=m.season,
            kickoff_at=m.kickoff_at,
            kickoff_has_time=m.kickoff_has_time,
            status=_status(m, now),
            home=TeamRef(id=m.home_team.id, name=m.home_team.name),
            away=TeamRef(id=m.away_team.id, name=m.away_team.name),
            home_goals=m.home_goals,
            away_goals=m.away_goals,
            odds_1x2=odds.get(m.id),
        )
        for m in matches
    ]


def to_result(m: Match) -> Result:
    return Result(
        match_id=m.id,
        kickoff_at=m.kickoff_at,
        home_id=m.home_team_id,
        away_id=m.away_team_id,
        home_goals=m.home_goals,
        away_goals=m.away_goals,
        home_shots=m.home_shots,
        away_shots=m.away_shots,
        home_shots_on_target=m.home_shots_on_target,
        away_shots_on_target=m.away_shots_on_target,
        home_corners=m.home_corners,
        away_corners=m.away_corners,
        home_xg=m.home_xg,
        away_xg=m.away_xg,
    )


# ---------- Endpoint ----------


@router.get("/competitions")
def list_competitions(_: CurrentUser, db: DbSession) -> list[CompetitionOut]:
    return [competition_out(c) for c in sorted(db.scalars(select(Competition)), key=competition_sort_key)]


@router.get("/matches")
def list_matches(
    _: CurrentUser,
    db: DbSession,
    view: Literal["upcoming", "results"] = "upcoming",
    competitions: str | None = Query(None, description="codici separati da virgola, es. ITA-A,ITA-B"),
    limit: int = Query(40, ge=1, le=200, description="partite massime per campionato"),
) -> list[CompetitionGroup]:
    now = datetime.now(UTC)
    query = select(Match).join(Competition)
    if competitions:
        query = query.where(Competition.code.in_(competitions.split(",")))
    if view == "upcoming":
        query = query.where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at >= now - RESULT_GRACE)
        query = query.order_by(Match.kickoff_at)
    else:
        # Giocate, più quelle iniziate da un po' di cui non abbiamo ancora il risultato
        query = query.where(
            or_(
                Match.status == MatchStatus.FINISHED,
                and_(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at < now - RESULT_GRACE, Match.kickoff_at > now - timedelta(days=30)),
            )
        ).order_by(Match.kickoff_at.desc())

    groups: dict[int, list[Match]] = defaultdict(list)
    for m in db.scalars(query.limit(limit * 10)).unique():
        if len(groups[m.competition_id]) < limit:
            groups[m.competition_id].append(m)

    ordered = sorted(groups.values(), key=lambda ms: competition_sort_key(ms[0].competition))
    return [CompetitionGroup(competition=competition_out(ms[0].competition), matches=match_cards(db, ms, now)) for ms in ordered]


@router.get("/matches/{match_id}")
def match_detail(match_id: int, _: CurrentUser, db: DbSession) -> MatchDetail:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Partita non trovata")
    now = datetime.now(UTC)
    before = match.kickoff_at  # la "fotografia" è sempre al calcio d'inizio: niente dati dal futuro
    teams = (match.home_team_id, match.away_team_id)

    # Tutte le partite finite delle due squadre prima del calcio d'inizio (qualsiasi campionato)
    team_games = db.scalars(
        select(Match).where(
            Match.status == MatchStatus.FINISHED,
            Match.kickoff_at < before,
            or_(Match.home_team_id.in_(teams), Match.away_team_id.in_(teams)),
        )
    ).all()
    # Partite finite dello stesso campionato e stagione, per classifica e medie stagionali
    season_games = db.scalars(
        select(Match).where(
            Match.status == MatchStatus.FINISHED,
            Match.kickoff_at < before,
            Match.competition_id == match.competition_id,
            Match.season == match.season,
        )
    ).all()
    # Partite dello stesso campionato già giocate (prima di questa) di cui la fonte non ha ancora il risultato
    missing_results = len(
        db.scalars(
            select(Match.id).where(
                Match.status == MatchStatus.SCHEDULED,
                Match.kickoff_at < min(before, now - RESULT_GRACE),
                Match.competition_id == match.competition_id,
                Match.season == match.season,
            )
        ).all()
    )
    team_results = [to_result(m) for m in team_games]
    season_results = [to_result(m) for m in season_games]
    by_id = {m.id: m for m in team_games}

    def side(team_id: int, venue: str) -> SideStats:
        entries = []
        for outcome, r in form(team_results, team_id, before):
            m = by_id[r.match_id]
            home = r.side(team_id) == "home"
            entries.append(
                FormEntry(
                    outcome=outcome,
                    match_id=r.match_id,
                    kickoff_at=r.kickoff_at,
                    opponent=(m.away_team if home else m.home_team).name,
                    venue="C" if home else "T",
                    score=f"{r.goals_for(team_id)}-{r.goals_against(team_id)}",
                )
            )
        team = match.home_team if team_id == match.home_team_id else match.away_team
        return SideStats(
            team=TeamRef(id=team.id, name=team.name),
            form=entries,
            season=summary(season_results, team_id, before),
            venue=summary(season_results, team_id, before, venue=venue),
        )

    names = {m.home_team_id: m.home_team for m in season_games} | {m.away_team_id: m.away_team for m in season_games}
    table = [
        StandingOut(
            rank=i + 1,
            team=TeamRef(id=row.team_id, name=names[row.team_id].name),
            played=row.played,
            won=row.won,
            drawn=row.drawn,
            lost=row.lost,
            goals_for=row.goals_for,
            goals_against=row.goals_against,
            points=row.points,
            form=row.form,
        )
        for i, row in enumerate(standings(season_results, before))
    ]

    h2h_ids = [r.match_id for r in head_to_head(team_results, *teams, before)]
    h2h = match_cards(db, [by_id[i] for i in h2h_ids], now)

    match_stats = None
    if match.status == MatchStatus.FINISHED:
        match_stats = {
            stat: [getattr(match, f"home_{stat}"), getattr(match, f"away_{stat}")]
            for stat in ("goals", "xg", "shots", "shots_on_target", "corners", "fouls", "yellow", "red")
        }
        match_stats["xg"] = [float(v) if v is not None else None for v in match_stats["xg"]]

    odds = _odds_table(db, match.id)
    return MatchDetail(
        match=match_cards(db, [match], now)[0],
        stats_as_of=before,
        missing_results=missing_results,
        home=side(match.home_team_id, "home"),
        away=side(match.away_team_id, "away"),
        head_to_head=h2h,
        standings=table,
        odds=odds,
        match_stats=match_stats,
        prediction=_prediction(db, match.id, odds),
    )


# Per il confronto: il mercato più preciso disponibile (D48), poi la media dei bookmaker
REFERENCE_ORDER = [("pinnacle", True), ("pinnacle", False), ("betfair_ex", True), ("betfair_ex", False), ("market_avg", True), ("market_avg", False)]


def _market_reference(odds: list[OddsRow]) -> dict[str, MarketReference]:
    out: dict[str, MarketReference] = {}
    for bookmaker, closing in REFERENCE_ORDER:
        for row in odds:
            prices = row.closing if closing else row.opening
            if row.bookmaker != bookmaker or row.market in out or len(prices) != {"1X2": 3, "OU2.5": 2}.get(row.market):
                continue
            fair = fair_probabilities(*prices.values())
            source = f"{row.label} · {'chiusura' if closing else 'apertura'}"
            out[row.market] = MarketReference(source=source, probabilities=dict(zip(prices, fair)))
    return out


def _prediction(db: Session, match_id: int, odds: list[OddsRow]) -> PredictionOut | None:
    p = db.scalar(select(MatchPrediction).where(MatchPrediction.match_id == match_id))
    if p is None:
        return None
    return PredictionOut(
        model_version=p.model_version,
        computed_at=p.computed_at,
        data_until=p.data_until,
        ratings=[p.home_rating, p.away_rating],
        expected_goals=[p.expected_home_goals, p.expected_away_goals],
        markets=p.markets,
        market=_market_reference(odds),
    )


def _odds_table(db: Session, match_id: int) -> list[OddsRow]:
    rows: dict[tuple[str, str], OddsRow] = {}
    for q in db.scalars(select(MatchOdds).where(MatchOdds.match_id == match_id)):
        row = rows.setdefault(
            (q.bookmaker, q.market),
            OddsRow(bookmaker=q.bookmaker, label=BOOKMAKER_LABELS.get(q.bookmaker, q.bookmaker), market=q.market, opening={}, closing={}),
        )
        (row.closing if q.is_closing else row.opening)[q.selection] = float(q.price)
    order = list(BOOKMAKER_LABELS)
    return sorted(rows.values(), key=lambda r: (r.market, order.index(r.bookmaker) if r.bookmaker in order else 99))
