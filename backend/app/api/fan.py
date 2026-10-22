"""Archie tifoso (D101-D102): i fatti delle due squadre e il giudizio di Archie per la pagina partita; stato della prova."""

import unicodedata
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.deps import CurrentUser, DbSession
from app.config import get_settings
from app.ingest.news import FACTS_WINDOW, TARGET_SIGNALS, fan_test
from app.models import Match, MatchAnalysis, MatchInsight, NewsItem, TeamFact

router = APIRouter(prefix="/api/fan", tags=["archie tifoso"])

KIND_LABELS = {
    "assente": "Assente",
    "rientro": "Rientro",
    "squalifica": "Squalifica",
    "allenatore_nuovo": "Nuovo allenatore",
    "allenatore_in_bilico": "Allenatore in bilico",
    "societa_in_crisi": "Società in difficoltà",
    "penalizzazione": "Penalizzazione",
    "acquisto": "Acquisto",
    "cessione": "Cessione",
    "clima_positivo": "Clima positivo",
    "clima_negativo": "Clima negativo",
}


class SimilarOut(BaseModel):
    detail: str
    published_at: datetime
    url: str
    source: str


class FactOut(BaseModel):
    team_id: int
    kind: str
    label: str
    player: str | None
    detail: str
    published_at: datetime
    url: str
    source: str
    similar: list[SimilarOut] = []  # altre notizie sulla stessa cosa (più vecchie), raggruppate sotto questa


# Una sola panchina e una sola società: tutte le notizie di questo tipo raccontano la stessa storia
ONE_STORY_KINDS = {"allenatore_in_bilico", "allenatore_nuovo", "societa_in_crisi", "penalizzazione"}


def _surname(name: str | None) -> str:
    """"Luciano Spalletti" e "Spalletti" → "spalletti"; "Conceição" e "Conceicao" → "conceicao"."""
    if not name:
        return ""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return plain.replace(".", " ").split()[-1] if plain.split() else ""


def group_facts(facts: list[FactOut]) -> list[FactOut]:
    """Notizie simili (stessa squadra, stesso tipo, stessa persona) in una riga sola: resta la più recente."""
    groups: dict[tuple, FactOut] = {}
    for f in sorted(facts, key=lambda x: x.published_at, reverse=True):
        key = (f.team_id, f.kind, "" if f.kind in ONE_STORY_KINDS else _surname(f.player))
        if key in groups:
            groups[key].similar.append(SimilarOut(detail=f.detail, published_at=f.published_at, url=f.url, source=f.source))
        else:
            groups[key] = f.model_copy(update={"similar": []})
    return list(groups.values())


class InsightOut(BaseModel):
    created_at: datetime
    side: str  # "home" | "away" | "none"
    strength: str
    reason: str


class FanTestOut(BaseModel):
    group: str  # "Serie C" (D101) o "Serie A e B" (D105): conteggi separati
    signals: int
    target: int
    mean_move: float | None  # punti di probabilità verso il lato indicato (0,01 = un punto)
    std_error: float | None


class MatchFanOut(BaseModel):
    facts: list[FactOut]
    insight: InsightOut | None
    test: FanTestOut


def _test(db, serie_c: bool = True) -> FanTestOut:
    found, est = fan_test(db, serie_c)
    return FanTestOut(group="Serie C" if serie_c else "Serie A e B", signals=len(found), target=TARGET_SIGNALS, mean_move=est.mean if est else None, std_error=est.std_error if est else None)


@router.get("/test")
def fan_test_status(_: CurrentUser, db: DbSession) -> list[FanTestOut]:
    return [_test(db, True), _test(db, False)]


@router.get("/match/{match_id}")
def match_fan(match_id: int, _: CurrentUser, db: DbSession) -> MatchFanOut:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Partita non trovata")
    # Fatti dei 10 giorni prima della partita (o di oggi, se è ancora lontana)
    until = min(match.kickoff_at, datetime.now(UTC))
    rows = db.execute(
        select(TeamFact, NewsItem).join(NewsItem, NewsItem.id == TeamFact.news_id)
        .where(TeamFact.team_id.in_([match.home_team_id, match.away_team_id]), TeamFact.published_at >= until - FACTS_WINDOW,
               TeamFact.published_at <= match.kickoff_at)
        .order_by(TeamFact.published_at.desc())
    ).all()  # fmt: skip
    facts = group_facts([FactOut(team_id=f.team_id, kind=f.kind, label=KIND_LABELS.get(f.kind, f.kind), player=f.player, detail=f.detail,
                                 published_at=f.published_at, url=n.url, source=n.source) for f, n in rows])  # fmt: skip
    last = db.scalars(select(MatchInsight).where(MatchInsight.match_id == match_id).order_by(MatchInsight.created_at.desc())).first()
    insight = InsightOut(created_at=last.created_at, side=last.side, strength=last.strength, reason=last.reason) if last else None
    return MatchFanOut(facts=facts, insight=insight, test=_test(db, match.competition.code.startswith("ITA-C")))


# ---------- Analisi della partita scritta da Archie (D107) ----------

ANALYSIS_FRESH = timedelta(hours=3)  # una nuova analisi al massimo ogni 3 ore per partita (tetto di spesa)
SELECTION_NAMES = {
    ("1X2", "1"): "1 (vince la squadra di casa)", ("1X2", "X"): "X (pareggio)", ("1X2", "2"): "2 (vince la squadra ospite)",
    ("DC", "1X"): "1X", ("DC", "X2"): "X2", ("DC", "12"): "12", ("OU2.5", "over"): "Over 2.5", ("OU2.5", "under"): "Under 2.5", ("OU1.5", "over"): "Over 1.5", ("OU1.5", "under"): "Under 1.5", ("OU3.5", "over"): "Over 3.5", ("OU3.5", "under"): "Under 3.5",
    ("GG", "yes"): "Gol (segnano entrambe)", ("GG", "no"): "No gol",
}  # fmt: skip


class AnalysisOut(BaseModel):
    created_at: datetime
    model: str
    summary: str
    points: list[str]
    verdict: str


def _analysis_out(a: MatchAnalysis) -> AnalysisOut:
    return AnalysisOut(created_at=a.created_at, model=a.model, summary=a.summary, points=[p for p in a.points.split("\n") if p], verdict=a.verdict)


def _pct(x: float | None) -> str:
    return "n.d." if x is None else f"{x * 100:.0f}%"


def _num(x: float | None) -> str:
    return "n.d." if x is None else f"{x:.2f}".replace(".", ",")


def analysis_brief(db, match: Match) -> str:
    """La scheda della partita per l'AI: solo numeri calcolati dal codice e fatti dalle notizie (principio 4)."""
    from app.api.football import match_detail
    from app.forecast.picks_service import match_market_picks
    from app.forecast.suggestions import suggestions

    d = match_detail(match.id, None, db)
    home, away = d.match.home.name, d.match.away.name
    lines = [f"Partita: {home} (casa) - {away} (ospite), {d.match.competition.name}, {d.match.kickoff_at:%d/%m/%Y %H:%M} UTC."]
    rank = {r.team.id: r for r in d.standings}
    for side, label in ((d.home, "Casa"), (d.away, "Ospite")):
        r = rank.get(side.team.id)
        if r:
            lines.append(f"{label} {side.team.name}: {r.rank}° in classifica con {r.points} punti in {r.played} partite "
                         f"({r.won}V {r.drawn}N {r.lost}P, gol {r.goals_for}-{r.goals_against}).")  # fmt: skip
        form = ", ".join(f"{f.outcome} {f.score} con {f.opponent} ({'casa' if f.venue == 'C' else 'fuori'})" for f in side.form[:5])
        if form:
            lines.append(f"  Ultime partite (dalla più recente): {form}.")
        s, v = side.season, side.venue
        lines.append(f"  Stagione: punti a partita {_num(s.points_per_game)}, gol fatti {_num(s.goals_for)} e subiti {_num(s.goals_against)} a partita, "
                     f"Over 2.5 {_pct(s.over_2_5)}, Gol {_pct(s.both_scored)}, porta inviolata {_pct(s.clean_sheets)}"
                     + (f", tiri {_num(s.shots_for)}, angoli {_num(s.corners_for)} a partita" if s.shots_for is not None else "") + ".")  # fmt: skip
        lines.append(f"  Solo {'in casa' if label == 'Casa' else 'in trasferta'}: {v.played} partite, punti a partita {_num(v.points_per_game)}, "
                     f"gol fatti {_num(v.goals_for)} e subiti {_num(v.goals_against)}.")  # fmt: skip
    if d.head_to_head:
        h2h = ", ".join(f"{m.home.name}-{m.away.name} {m.home_goals}-{m.away_goals}" for m in d.head_to_head[:5] if m.home_goals is not None)
        if h2h:
            lines.append(f"Precedenti recenti: {h2h}.")
    picks = match_market_picks(db, match, get_settings().radar_bookmaker_list)
    for p in picks:
        probs = ", ".join(f"{SELECTION_NAMES.get((p.market, k), k)} {_pct(v)}" for k, v in p.probabilities.items())
        lines.append(f"Probabilità {p.market} (fonte: {p.source}): {probs}.")
    for s in suggestions(picks):
        value = "con valore" if s.has_value else "senza valore (quota nella norma)"
        lines.append(f"Pronostico {'più sicuro' if s.kind == 'sicuro' else 'più spinto'}: {SELECTION_NAMES.get((s.market, s.selection), s.selection)}, "
                     f"probabilità {_pct(s.probability)}, quota migliore {_num(s.offer.price)} ({s.offer.bookmaker}), {value}.")  # fmt: skip
    rows = db.execute(select(TeamFact).where(TeamFact.team_id.in_([match.home_team_id, match.away_team_id]),
                                             TeamFact.published_at >= min(match.kickoff_at, datetime.now(UTC)) - FACTS_WINDOW,
                                             TeamFact.published_at <= match.kickoff_at).order_by(TeamFact.published_at)).scalars().all()  # fmt: skip
    latest = {}
    for f in rows:  # la stessa notizia da più fonti: vale la più recente
        latest[(f.team_id, f.kind, (f.player or "").lower())] = f
    for f in sorted(latest.values(), key=lambda x: x.published_at):
        team = home if f.team_id == match.home_team_id else away
        lines.append(f"Notizia {f.published_at:%d/%m} su {team}: {KIND_LABELS.get(f.kind, f.kind)}{f' ({f.player})' if f.player else ''}: {f.detail}")
    last = db.scalars(select(MatchInsight).where(MatchInsight.match_id == match.id).order_by(MatchInsight.created_at.desc())).first()
    if last:
        who = home if last.side == "home" else away if last.side == "away" else "nessuna"
        lines.append(f"Giudizio di Archie sulle notizie: favorita {who} ({last.strength or 'nessun effetto'}). {last.reason}")
    return "\n".join(lines)


@router.get("/match/{match_id}/analysis")
def get_analysis(match_id: int, _: CurrentUser, db: DbSession) -> AnalysisOut | None:
    last = db.scalars(select(MatchAnalysis).where(MatchAnalysis.match_id == match_id).order_by(MatchAnalysis.created_at.desc())).first()
    return _analysis_out(last) if last else None


@router.post("/match/{match_id}/analysis")
def make_analysis(match_id: int, user: CurrentUser, db: DbSession) -> AnalysisOut:
    from app.ai.analysis import write_analysis
    from app.ai.client import Ai, AiError
    from app.ai.gateway import BudgetExceeded

    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Partita non trovata")
    last = db.scalars(select(MatchAnalysis).where(MatchAnalysis.match_id == match_id).order_by(MatchAnalysis.created_at.desc())).first()
    now = datetime.now(UTC)
    if last and now - last.created_at < ANALYSIS_FRESH:
        return _analysis_out(last)  # ancora fresca: niente nuova spesa
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="Chiave Claude non configurata")
    try:
        a = write_analysis(Ai(db, settings.anthropic_api_key, settings), settings.ai_model, analysis_brief(db, match))
    except BudgetExceeded as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AiError as exc:
        raise HTTPException(status_code=502, detail=f"Analisi non riuscita: {exc}") from exc
    row = MatchAnalysis(match_id=match_id, created_at=now, model=settings.ai_model, summary=a.summary,
                        points="\n".join(p.replace("\n", " ") for p in a.points), verdict=a.verdict)  # fmt: skip
    db.add(row)
    db.commit()
    return _analysis_out(row)
