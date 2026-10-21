"""Importa i dati di football-data.co.uk nel database (partite, squadre, quote)."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.adapters.football_data import FIRST_SEASON, LEAGUES, SOURCE, FDMatch, FootballDataAdapter, season_label, season_of
from app.ingest.teams import TeamResolver, ensure_competitions
from app.models import Competition, Match, MatchOdds, MatchStatus


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0
    odds: int = 0
    skipped: int = 0

    def add(self, other: "ImportReport") -> None:
        self.created += other.created
        self.updated += other.updated
        self.odds += other.odds
        self.skipped += other.skipped


def import_matches(db: Session, rows: Iterable[FDMatch], season: str | None = None) -> ImportReport:
    """Salva le partite: crea le nuove, aggiorna quelle esistenti, sostituisce le quote di questa fonte.

    season: stagione del file. Se manca (file delle prossime partite) si ricava dalla data.
    """
    competitions = ensure_competitions(db)
    resolvers: dict[str, TeamResolver] = {}  # una anagrafica per paese
    report = ImportReport()
    existing: dict[tuple[int, str, int, int], Match] = {}
    loaded: set[tuple[int, str]] = set()
    touched: dict[tuple[int, str, int, int], tuple[Match, FDMatch]] = {}  # una sola riga per partita: vince l'ultima

    for row in rows:
        if row.league not in LEAGUES:
            continue
        competition = competitions[LEAGUES[row.league]]
        match_season = season or season_label(season_of(row.kickoff_at.date()))
        if (competition.id, match_season) not in loaded:
            # Carica in un colpo solo le partite già presenti per campionato e stagione
            for m in db.scalars(select(Match).where(Match.competition_id == competition.id, Match.season == match_season)):
                existing[(m.competition_id, m.season, m.home_team_id, m.away_team_id)] = m
            loaded.add((competition.id, match_season))

        teams = resolvers.setdefault(competition.country, TeamResolver(db, SOURCE, competition.country))
        home, away = teams.resolve(row.home), teams.resolve(row.away)
        key = (competition.id, match_season, home.id, away.id)
        match = existing.get(key)
        if match is None:
            match = Match(competition_id=competition.id, season=match_season, home_team_id=home.id, away_team_id=away.id)
            db.add(match)
            existing[key] = match
            report.created += 1
        elif key not in touched:
            report.updated += 1

        touched[key] = (match, row)
        if match.status == MatchStatus.FINISHED and not row.finished:
            continue  # file delle prossime partite non ancora aggiornato: il risultato (da API-Football) resta (D133)
        match.kickoff_at = row.kickoff_at
        match.kickoff_has_time = row.kickoff_has_time
        match.status = MatchStatus.FINISHED if row.finished else MatchStatus.SCHEDULED
        match.home_goals, match.away_goals = row.home_goals, row.away_goals
        match.ht_home_goals, match.ht_away_goals = row.ht_home_goals, row.ht_away_goals
        match.home_xg, match.away_xg = row.home_xg, row.away_xg
        for name, value in row.stats.items():
            setattr(match, name, value)
        match.referee = row.referee

    db.flush()  # assegna gli id alle partite nuove
    ids = [match.id for match, _ in touched.values()]
    for start in range(0, len(ids), 500):
        db.execute(delete(MatchOdds).where(MatchOdds.source == SOURCE, MatchOdds.match_id.in_(ids[start : start + 500])))
    values = [
        {
            "match_id": match.id,
            "source": SOURCE,
            "bookmaker": q.bookmaker,
            "market": q.market,
            "selection": q.selection,
            "price": q.price,
            "is_closing": q.is_closing,
        }
        for match, row in touched.values()
        for q in row.odds
    ]
    if values:
        db.execute(insert(MatchOdds), values)
    report.odds = len(values)
    db.commit()
    return report


def sync_football_data(
    db: Session,
    adapter: FootballDataAdapter,
    first_season: int = FIRST_SEASON,
    now: datetime | None = None,
    log=print,
    skip_imported: bool = False,
) -> ImportReport:
    """Scarica (o legge dalla cache) tutte le stagioni dei campionati di football-data e le prossime partite.

    skip_imported: le stagioni concluse già importate (con le quote) non si rileggono. Serve al giro automatico,
    che altrimenti riscriverebbe ogni volta ~80.000 partite che non cambiano più.
    """
    current = season_of((now or datetime.now(UTC)).date())
    imported: set[tuple[str, str]] = set()
    if skip_imported:
        imported = {
            (code, season)
            for code, season in db.execute(
                select(Competition.code, Match.season)
                .join(Match, Match.competition_id == Competition.id)
                .join(MatchOdds, MatchOdds.match_id == Match.id)
                .where(MatchOdds.source == SOURCE)
                .distinct()
            )
        }
    total = ImportReport()
    for league in LEAGUES:
        for year in range(first_season, current + 1):
            if year < current and (LEAGUES[league], season_label(year)) in imported:
                continue
            report = import_matches(db, adapter.season(league, year, current), season=season_label(year))
            log(f"{LEAGUES[league]} {season_label(year)}: {report.created} nuove, {report.updated} aggiornate, {report.odds} quote")
            total.add(report)
    report = import_matches(db, adapter.fixtures())
    log(f"Prossime partite: {report.created} nuove, {report.updated} aggiornate")
    total.add(report)
    return total
