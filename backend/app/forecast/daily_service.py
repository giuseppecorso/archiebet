"""Bacheca Daily (D153): pubblica le schedine del giorno dallo studio e dalle occasioni, poi le chiude con i risultati."""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.betting.calc import at_least, selection_outcome, system_range
from app.config import get_settings
from app.forecast.daily import KINDS, OPEN, Kind, due, leg_status, slip_status
from app.forecast.multiplier import best_slip, price_rows
from app.forecast.radar import BookOdds, RadarSignal, qualifies, scan
from app.forecast.radar_markets import is_secondary
from app.forecast.radar_service import load_book_odds
from app.forecast.study import auto_legs, choose_varied, event_text, leg_price, playable_price, up_to_target
from app.forecast.study_service import load_studies
from app.models import DailySlip, Match, MatchStatus

MAX_RANKED = 30
MIN_PRICE = 1.40  # D172: nelle schedine dello studio niente quote più basse


def _leg(m: Match, market: str, selection: str, event: str, p: float, price: float) -> dict:
    return {
        "match_id": m.id, "kickoff_at": m.kickoff_at.isoformat(), "competition": m.competition.name,
        "home": m.home_team.name, "away": m.away_team.name, "market": market, "selection": selection,
        "event": event, "p": round(p, 4), "price": round(price, 2), "status": OPEN,
    }  # fmt: skip


def choose_study_legs(kind: Kind, studies: Sequence[tuple[int, list[dict]]], min_price: float = MIN_PRICE) -> list[tuple[int, dict]]:
    """Quali pronostici entrano nella schedina: la regola è una sola, per la bacheca vera e per la simulazione (D171)."""
    kept = [(mid, above) for mid, picks in studies if (above := [p for p in picks if playable_price(p) >= min_price])]
    ranked = choose_varied(kept, kind.level, MAX_RANKED)  # niente tre volte lo stesso pronostico
    if kind.target:
        return up_to_target(ranked, kind.target)
    chosen = auto_legs(ranked, kind.level)
    if len(chosen) < kind.min_legs:
        chosen = ranked[: kind.min_legs]
    return chosen[: kind.max_legs]


def study_legs(db: Session, kind: Kind, start: datetime, end: datetime) -> list[dict]:
    """Dallo studio di Archie: i pronostici più solidi del livello, quante partite secondo il tipo di schedina."""
    studies = load_studies(db, start, end)
    matches = {m.id: m for m, _ in studies}
    chosen = choose_study_legs(kind, [(m.id, d["picks"]) for m, d in studies])
    chosen.sort(key=lambda c: matches[c[0]].kickoff_at)
    return [_leg(matches[mid], p["market"], p["selection"], p["event"], p["p_archie"], leg_price(p)) | {"from_market": bool(p.get("from_market"))}
            for mid, p in chosen]  # fmt: skip


def best_value[T](kind: Kind, books: Iterable[tuple[T, BookOdds]], playable: Sequence[str]) -> list[tuple[T, RadarSignal]]:
    """I pronostici più convenienti (uno per partita, mercati principali, niente quote sospette): stessa regola dal vivo e in simulazione."""
    best = []
    for item, book in books:
        found = [c for c in scan(book, playable=playable) if qualifies(c.price, c.value) and not c.suspicious and not is_secondary(c.market)]
        if found:
            c = max(found, key=lambda c: c.value)
            best.append((c.value, item, c))
    best.sort(key=lambda x: x[0], reverse=True)
    return [(item, c) for _, item, c in best[: kind.max_legs]]


def clv_legs(db: Session, kind: Kind, start: datetime, end: datetime) -> list[dict]:
    """Le occasioni migliori di oggi, da giocare singole."""
    matches = list(db.scalars(select(Match).where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > start, Match.kickoff_at <= end)))
    books = load_book_odds(db, [m.id for m in matches], closing=False)
    chosen = sorted(best_value(kind, [(m, books.get(m.id, {})) for m in matches], get_settings().radar_bookmaker_list), key=lambda x: x[0].kickoff_at)
    return [_leg(m, c.market, c.selection, event_text(c.market, c.selection, m.home_team.name, m.away_team.name), c.fair_probability, c.price)
            for m, c in chosen]  # fmt: skip


def multiplier_legs(db: Session, kind: Kind, start: datetime, end: datetime) -> list[dict]:
    """La schedina 6-10 (D177): le partite di oggi con la quota più conveniente rispetto al prezzo giusto."""
    matches = {m.id: m for m in db.scalars(select(Match).where(Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > start, Match.kickoff_at <= end))}
    books = load_book_odds(db, list(matches), closing=False)
    rows = [r for m in matches.values() for r in price_rows(m.id, m.kickoff_at.isoformat(), books.get(m.id, {}), get_settings().radar_bookmaker_list)]
    slip = best_slip(rows, kind.multiplier_legs, "valore") if kind.multiplier_legs else None
    return [_leg(matches[r["match_id"]], r["market"], r["selection"], event_text(r["market"], r["selection"], matches[r["match_id"]].home_team.name, matches[r["match_id"]].away_team.name), r["sharp"], r["price"])
            for r in sorted(slip or [], key=lambda r: r["when"])]  # fmt: skip


def slip_totals(kind: Kind, legs: Sequence[dict]) -> tuple[float, float] | None:
    """Quota totale e probabilità di una schedina (None se le partite non bastano per il sistema)."""
    total, p = 1.0, 1.0
    for leg in legs:
        total *= leg["price"]
        p *= leg["p"]
    if kind.singles:
        return 1.0, sum(leg["p"] for leg in legs) / len(legs)  # singole: niente quota totale, probabilità media
    if kind.system:
        if len(legs) <= kind.system:
            return None
        # quota = quanto torna 1 € con tutto indovinato; probabilità = indovinarne almeno k
        total = float(system_range(Decimal(100), [Decimal(str(leg["price"])) for leg in legs], kind.system)[1]) / 100
        p = at_least([leg["p"] for leg in legs], kind.system)
    return total, p


def publish_due(db: Session, now: datetime | None = None) -> list[str]:
    """Pubblica le schedine del momento che non ci sono ancora. Restituisce i tipi pubblicati."""
    now = now or datetime.now(UTC)
    published = []
    for kind, period, start, end in due(now):
        if db.scalar(select(DailySlip.id).where(DailySlip.kind == kind.key, DailySlip.period == period)):
            continue
        legs = study_legs(db, kind, start, end) if kind.level else multiplier_legs(db, kind, start, end) if kind.multiplier_legs else clv_legs(db, kind, start, end)
        if not legs:
            continue  # niente da proporre adesso: si riprova al prossimo giro dello stesso giorno
        totals = slip_totals(kind, legs)
        if totals is None:
            continue  # troppe poche partite per il sistema: si riprova al prossimo giro
        total, p = totals
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
