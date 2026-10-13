"""Quote di OddsPapi nel database: si agganciano alle partite che abbiamo già (il calendario lo danno le altre fonti).

- Elenco delle partite in programma: una volta al giorno (2 richieste: massimo 5 campionati per richiesta).
- Partite dei prossimi 7 giorni: quote attuali di Pinnacle e dei bookmaker dove Giuse gioca (Sisal, Eurobet)
  dallo storico gratuito (1 chiamata per partita fino a 3 bookmaker, 5,5 secondi), salvate come "non di chiusura".
- Partite iniziate da almeno 2 ore: quota di chiusura di Pinnacle = ultimo prezzo prima del calcio d'inizio,
  il riferimento per il CLV (D48).
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.adapters.oddspapi import ITALIAN, SHARP, SOURCE, TOURNAMENTS, OddsPapiAdapter, OPFixture, Prices, prices_at
from app.ingest.teams import normalize_team_name
from app.models import Competition, Match, MatchOdds, MatchSource, MatchStatus, Team, TeamAlias

LINK_WINDOW = timedelta(hours=48)  # stessa partita se il calcio d'inizio differisce al massimo di tanto
HORIZON = timedelta(days=7)  # quote attuali solo per le partite dei prossimi giorni
UPCOMING_MAX_AGE = timedelta(hours=23)  # elenco partite una volta al giorno: ~62 richieste al mese
HISTORY_MAX_AGE = timedelta(hours=5)  # "Aggiorna ora" subito dopo un giro automatico non riscarica
DEFAULT_BOOKMAKERS = ("sisal", "eurobet")  # D66


def current_slugs(bookmakers: Sequence[str]) -> list[str]:
    """Slug OddsPapi da chiedere allo storico: Pinnacle (riferimento) + i bookmaker dove si gioca."""
    slug_of = {name: slug for slug, name in ITALIAN.items()}
    return list(SHARP) + [slug_of[b] for b in bookmakers if b in slug_of]
CLOSING_DELAY = timedelta(hours=2)  # la chiusura si chiede a partita iniziata da un po'
CLOSING_LOOKBACK = timedelta(days=14)  # oltre, se manca la chiusura, si rinuncia
CLOSING_SLUGS = ["pinnacle"]


@dataclass
class OddsPapiReport:
    linked: int = 0  # partite collegate in questo giro
    not_in_calendar: int = 0  # partite di OddsPapi che non abbiamo (ancora) in calendario
    unknown_teams: list[str] = field(default_factory=list)
    current: int = 0  # partite con quote attuali aggiornate
    closing: int = 0  # partite con chiusura salvata


def _team_index(db: Session) -> tuple[dict[str, int], dict[tuple[str, str], int]]:
    """(id OddsPapi → squadra, (paese, nome ripulito) → squadra) con i nomi di tutte le fonti."""
    by_alias = {a.alias: a.team_id for a in db.scalars(select(TeamAlias).where(TeamAlias.source == SOURCE))}
    by_name: dict[tuple[str, str], int] = {}
    for team in db.scalars(select(Team)):
        by_name.setdefault((team.country, normalize_team_name(team.name)), team.id)
    for alias, country, team_id in db.execute(select(TeamAlias.alias, Team.country, Team.id).join(Team, TeamAlias.team_id == Team.id)):
        by_name.setdefault((country, normalize_team_name(alias)), team_id)
    return by_alias, by_name


def link_fixtures(db: Session, fixtures: Iterable[OPFixture], names: dict[str, str], report: OddsPapiReport) -> dict[str, Match]:
    """Collega le partite di OddsPapi alle nostre (stesso campionato, stesse squadre, data vicina)."""
    competitions = {c.code: c for c in db.scalars(select(Competition))}
    links = {s.external_id: s.match_id for s in db.scalars(select(MatchSource).where(MatchSource.source == SOURCE))}
    by_alias, by_name = _team_index(db)
    out: dict[str, Match] = {}
    for fx in fixtures:
        if fx.tournament_id not in TOURNAMENTS:
            continue
        if fx.id in links:
            out[fx.id] = db.get(Match, links[fx.id])
            continue
        competition = competitions.get(TOURNAMENTS[fx.tournament_id])
        if competition is None:
            continue
        teams = []
        for pid in (fx.home_id, fx.away_id):
            name = names.get(str(pid), "")
            team = by_alias.get(str(pid))
            if team is None and name:
                team = by_name.get((competition.country, normalize_team_name(name)))
            if team is None:
                report.unknown_teams.append(name or f"id {pid}")
            teams.append(team)
        if None in teams:
            continue
        match = db.scalar(
            select(Match).where(
                Match.competition_id == competition.id,
                Match.home_team_id == teams[0],
                Match.away_team_id == teams[1],
                Match.kickoff_at.between(fx.start_time - LINK_WINDOW, fx.start_time + LINK_WINDOW),
            )
        )
        if match is None:
            report.not_in_calendar += 1
            continue
        db.add(MatchSource(match_id=match.id, source=SOURCE, external_id=fx.id))
        for pid, team in zip((fx.home_id, fx.away_id), teams):
            if str(pid) not in by_alias:
                db.add(TeamAlias(team_id=team, source=SOURCE, alias=str(pid)))
                by_alias[str(pid)] = team
        links[fx.id] = match.id
        out[fx.id] = match
        report.linked += 1
    db.flush()
    return out


def replace_odds(db: Session, match_id: int, prices: Prices, closing: bool) -> int:
    """Sostituisce le quote OddsPapi della partita (attuali o di chiusura). Restituisce quante ne ha scritte."""
    db.execute(delete(MatchOdds).where(MatchOdds.match_id == match_id, MatchOdds.source == SOURCE, MatchOdds.is_closing.is_(closing)))
    rows = [
        {"match_id": match_id, "source": SOURCE, "bookmaker": bookmaker, "market": market, "selection": selection,
         "price": Decimal(str(price)), "is_closing": closing}
        for bookmaker, markets in prices.items()
        for market, selections in markets.items()
        for selection, price in selections.items()
        if price > 1
    ]  # fmt: skip
    if rows:
        db.execute(insert(MatchOdds), rows)
    return len(rows)


def sync_oddspapi(
    db: Session,
    adapter: OddsPapiAdapter,
    now: datetime,
    log: Callable[[str], None] = print,
    bookmakers: Sequence[str] = DEFAULT_BOOKMAKERS,
) -> OddsPapiReport:
    report = OddsPapiReport()
    slugs = current_slugs(bookmakers)
    fixtures, current = adapter.upcoming(UPCOMING_MAX_AGE)
    names = adapter.participants()
    if any(str(p) not in names for fx in fixtures for p in (fx.home_id, fx.away_id)):
        names = adapter.participants(max_age=timedelta(0))  # squadra nuova: rinfresco i nomi
    links = link_fixtures(db, fixtures, names, report)
    db.commit()

    # Quote attuali delle partite in programma
    for fixture_id, match in links.items():
        if match.status != MatchStatus.SCHEDULED or not (now < match.kickoff_at <= now + HORIZON):
            continue
        prices = prices_at(adapter.history(fixture_id, slugs, HISTORY_MAX_AGE), now)
        for bookmaker, markets in current.get(fixture_id, {}).items():  # elenco del giorno: solo se lo storico non li ha
            for market, selections in markets.items():
                prices.setdefault(bookmaker, {}).setdefault(market, selections)
        if replace_odds(db, match.id, prices, closing=False):
            report.current += 1
        db.commit()

    # Chiusura di Pinnacle per le partite iniziate
    with_closing = select(MatchOdds.match_id).where(MatchOdds.source == SOURCE, MatchOdds.is_closing.is_(True))
    pending = db.execute(
        select(MatchSource.external_id, Match)
        .join(Match, MatchSource.match_id == Match.id)
        .where(
            MatchSource.source == SOURCE,
            Match.kickoff_at < now - CLOSING_DELAY,
            Match.kickoff_at > now - CLOSING_LOOKBACK,
            Match.status != MatchStatus.CANCELLED,
            Match.id.not_in(with_closing),
        )
    ).all()
    for fixture_id, match in pending:
        prices = prices_at(adapter.history(fixture_id, CLOSING_SLUGS, timedelta(days=365)), match.kickoff_at)
        if replace_odds(db, match.id, prices, closing=True):
            report.closing += 1
        db.commit()

    if report.unknown_teams:
        log(f"OddsPapi: squadre non riconosciute {sorted(set(report.unknown_teams))}")
    return report
