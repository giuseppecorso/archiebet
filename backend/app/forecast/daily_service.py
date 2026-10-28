"""Bacheca Daily (D153): pubblica le schedine del giorno dallo studio e dalle occasioni, poi le chiude con i risultati."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.betting.calc import at_least, selection_outcome, system_range
from app.config import get_settings
from app.forecast.daily import KINDS, OPEN, Kind, due, leg_status, slip_status
from app.forecast.radar import qualifies, scan
from app.forecast.radar_markets import is_secondary
from app.forecast.radar_service import load_book_odds
from app.forecast.study import auto_legs, choose_varied, event_text, leg_price, up_to_target
from app.forecast.study_service import load_studies
from app.models import DailySlip, Match, MatchStatus

MAX_RANKED = 30


def _leg(m: Match, market: str, selection: str, event: str, p: float, price: float) -> dict:
    return {
        "match_id": m.id, "kickoff_at": m.kickoff_at.isoformat(), "competition": m.competition.name,
        "home": m.home_team.name, "away": m.away_team.name, "market": market, "selection": selection,
        "event": event, "p": round(p, 4), "price": round(price, 2), "status": OPEN,
    }  # fmt: skip


def study_legs(db: Session, kind: Kind, start: datetime, end: datetime) -> list[dict]:
    """Dallo studio di Archie: i pronostici più solidi del livello, quante partite secondo il tipo di schedina."""
    studies = load_studies(db, start, end)
    matches = {m.id: m for m, _ in studies}
    ranked = choose_varied([(m.id, d["picks"]) for m, d in studies], kind.level, MAX_RANKED)  # niente tre volte lo stesso pronostico
    if kind.target:
        chosen = up_to_target(ranked, kind.target)
    else:
        chosen = auto_legs(ranked, kind.level)
        if len(chosen) < kind.min_legs:
            chosen = ranked[: kind.min_legs]
        chosen = chosen[: kind.max_legs]
    chosen.sort(key=lambda c: matches[c[0]].kickoff_at)
    return [_leg(matches[mid], p["market"], p["selection"], p["event"], p["p_archie"], leg_price(p)) for mid, p in chosen]


def clv_legs(db: Session, kind: Kind, start: datetime, end: datetime) -> list[dict]:
    """Le occasioni migliori di oggi (una per partita, mercati principali, niente quote sospette), da giocare singole."""
    matches = list(db.scalars(select(Match).where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > start, Match.kickoff_at <= end)))
    books = load_book_odds(db, [m.id for m in matches], closing=False)
    best = []
    for m in matches:
        found = [c for c in scan(books.get(m.id, {}), playable=get_settings().radar_bookmaker_list)
                 if qualifies(c.price, c.value) and not c.suspicious and not is_secondary(c.market)]  # fmt: skip
        if found:
            c = max(found, key=lambda c: c.value)
            best.append((c.value, m, c))
    best.sort(key=lambda x: x[0], reverse=True)
    chosen = sorted(best[: kind.max_legs], key=lambda x: x[1].kickoff_at)
    return [_leg(m, c.market, c.selection, event_text(c.market, c.selection, m.home_team.name, m.away_team.name), c.fair_probability, c.price)
            for _, m, c in chosen]  # fmt: skip


def publish_due(db: Session, now: datetime | None = None) -> list[str]:
    """Pubblica le schedine del momento che non ci sono ancora. Restituisce i tipi pubblicati."""
    now = now or datetime.now(UTC)
    published = []
    for kind, period, start, end in due(now):
        if db.scalar(select(DailySlip.id).where(DailySlip.kind == kind.key, DailySlip.period == period)):
            continue
        legs = study_legs(db, kind, start, end) if kind.level else clv_legs(db, kind, start, end)
        if not legs:
            continue  # niente da proporre adesso: si riprova al prossimo giro dello stesso giorno
        total, p = 1.0, 1.0
        for leg in legs:
            total *= leg["price"]
            p *= leg["p"]
        if kind.singles:
            total, p = 1.0, sum(leg["p"] for leg in legs) / len(legs)  # singole: niente quota totale, probabilità media
        if kind.system:
            if len(legs) <= kind.system:
                continue  # troppe poche partite per il sistema: si riprova al prossimo giro
            # quota = quanto torna 1 € con tutto indovinato; probabilità = indovinarne almeno k
            total = float(system_range(Decimal(100), [Decimal(str(leg["price"])) for leg in legs], kind.system)[1]) / 100
            p = at_least([leg["p"] for leg in legs], kind.system)
        db.add(DailySlip(kind=kind.key, period=period, published_at=now, legs=legs, total_odds=round(total, 2), win_probability=round(p, 4), status=OPEN))
        published.append(kind.key)
    db.commit()
    return published


def settle_daily(db: Session, now: datetime | None = None) -> int:
    """Esito di ogni pronostico appena la partita finisce; chiude le schedine. Restituisce quante si sono chiuse."""
    now = now or datetime.now(UTC)
    slips = list(db.scalars(select(DailySlip).where(DailySlip.status == OPEN)))
    ids = {leg["match_id"] for s in slips for leg in s.legs if leg["status"] == OPEN}
    matches = {m.id: m for m in db.scalars(select(Match).where(Match.id.in_(ids)))} if ids else {}
    closed = 0
    for s in slips:
        legs = []
        for leg in s.legs:
            m = matches.get(leg["match_id"])
            if leg["status"] == OPEN and m is not None:
                outcome = None
                if m.status == MatchStatus.FINISHED and m.home_goals is not None:
                    ht = (m.ht_home_goals, m.ht_away_goals) if m.ht_home_goals is not None else None
                    try:
                        outcome = selection_outcome(leg["market"], leg["selection"], m.home_goals, m.away_goals, ht)
                    except ValueError:
                        outcome = None  # manca il primo tempo: si riprova più tardi
                leg = {**leg, "status": leg_status(m.status, outcome)}
            legs.append(leg)
        s.legs = legs  # lista nuova: SQLAlchemy salva il JSON cambiato
        s.status = slip_status(legs, KINDS[s.kind].singles, KINDS[s.kind].system)
        if s.status != OPEN:
            s.settled_at = now
            closed += 1
    db.commit()
    return closed
