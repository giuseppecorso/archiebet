"""Chiedi ad Archie (Fase 6): domande in italiano, risposte con i dati dell'app letti dagli strumenti."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.auth.deps import AdminUser, CurrentUser, DbSession
from app.config import get_settings
from app.models import AiQuestion, Bet, Match, MatchStatus, MatchStudy, Team, TeamFact
from app.betting.calc import market_name

router = APIRouter(prefix="/api/ask", tags=["chiedi ad archie"])

HISTORY = 3  # domande precedenti passate come contesto (per le domande di seguito)
MARKET_NAMES = {"1X2": "1X2", "DC": "doppia chance", "OU1.5": "Under/Over 1.5", "OU2.5": "Under/Over 2.5", "OU3.5": "Under/Over 3.5", "GG": "Gol/No gol"}


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=600)
    match_id: int | None = None


class AnswerOut(BaseModel):
    id: int
    question: str
    answer: str
    match_id: int | None
    created_at: datetime


def _out(q: AiQuestion) -> AnswerOut:
    return AnswerOut(id=q.id, question=q.question, answer=q.answer, match_id=q.match_id, created_at=q.created_at)


def _when(m: Match) -> str:
    return f"{m.kickoff_at:%d/%m %H:%M} UTC"


def build_tools(db, user_id: int):
    """Gli strumenti di Archie: ognuno legge dal database e restituisce testo con numeri calcolati dal codice."""
    from app.ai.ask import Tool
    from app.api.fan import KIND_LABELS, analysis_brief
    from app.api.picks import match_numbers, match_players
    from app.betting.service import summarize
    from app.forecast.picks_service import upcoming_picks
    from app.ingest.news import FACTS_WINDOW

    def find_teams(name: str) -> list[Team]:
        return list(db.scalars(select(Team).where(Team.name.ilike(f"%{name.strip()}%")).limit(5)))

    def cerca_partite(squadra: str) -> str:
        teams = find_teams(squadra)
        if not teams:
            return f"Nessuna squadra trovata con '{squadra}'."
        lines = []
        now = datetime.now(UTC)
        for t in teams:
            side = or_(Match.home_team_id == t.id, Match.away_team_id == t.id)
            nxt = db.scalars(select(Match).where(side, Match.status == MatchStatus.SCHEDULED, Match.kickoff_at > now).order_by(Match.kickoff_at).limit(2)).all()
            last = db.scalars(select(Match).where(side, Match.status == MatchStatus.FINISHED).order_by(Match.kickoff_at.desc()).limit(3)).all()
            lines.append(f"{t.name} ({t.country}):")
            lines += [f"  prossima: id {m.id}, {m.home_team.name} - {m.away_team.name}, {m.competition.name}, {_when(m)}" for m in nxt]
            lines += [f"  giocata: id {m.id}, {m.home_team.name} - {m.away_team.name} {m.home_goals}-{m.away_goals}, {m.competition.name}, {m.kickoff_at:%d/%m}" for m in last]
        return "\n".join(lines)

    def scheda_partita(match_id: int) -> str:
        match = db.get(Match, match_id)
        if match is None:
            return "Partita non trovata."
        text = [analysis_brief(db, match)]
        study = db.get(MatchStudy, match_id)
        if study is not None:  # lo studio di Archie (D137): i pronostici proposti e i loro motivi, calcolati dal codice
            d = study.data
            text.append(f"Studio di Archie: gol attesi casa {d['lam']:.2f}, ospite {d['mu']:.2f}; forma {d['form_home']} / {d['form_away']}.")
            from app.forecast.study import pick_strength

            for level in ("cauto", "equilibrato", "rischioso"):
                best = sorted((x for x in d["picks"] if x["level"] == level), key=pick_strength, reverse=True)[:3]
                for x in best:
                    text.append(f"Pronostico {level}: {x['event']} — probabilità dello studio {x['p_archie']:.0%} (modello {x['p_model']:.0%}). Motivi: {' '.join(x['reasons'])}")
        for n in match_numbers(match_id, None, db):
            total = [line for line in n.lines if line.side == "totale"]
            def quoted(line) -> str:
                offers = "; ".join(f"{bm} over {o.get('over', 0):.2f} under {o.get('under', 0):.2f}" for bm, o in line.offers.items())
                return f" [quote: {offers}]" if offers else ""

            lines = ", ".join(f"Over {line.line} {line.p_over:.0%} (giusta over {line.fair_over:.2f}, under {line.fair_under:.2f}){quoted(line)}" for line in total)
            text.append(f"{n.label} attesi: casa {n.home:.1f}, ospite {n.away:.1f}; {lines}.")
        players = match_players(match_id, None, db)
        if players:
            top = [p for p in players if not p.absent][:6]
            text.append("Tiratori attesi: " + "; ".join(f"{p.name} ({p.side}) {p.exp_shots:.1f} tiri, almeno 1 tiro {p.p_shot:.0%}, almeno 1 in porta {p.p_on:.0%}" for p in top))
            out = [p.name for p in players if p.absent]
            if out:
                text.append("Assenti secondo le notizie: " + ", ".join(out))
        return "\n".join(text)

    def occasioni() -> str:
        now = datetime.now(UTC)
        found = []
        for m, picks in upcoming_picks(db, now, now + timedelta(days=4), get_settings().radar_bookmaker_list):
            for p in picks:
                for sel, offers in p.offers.items():
                    for o in offers:
                        if o.verdict in ("valore", "sopra la media"):
                            kind = "valore" if o.verdict == "valore" else "sopra la media italiana (solo indicazione)"
                            found.append((o.value, f"id {m.id} {m.home_team.name}-{m.away_team.name} ({_when(m)}): {(MARKET_NAMES.get(p.market) or market_name(p.market))} {sel} "
                                                   f"a {o.price:.2f} su {o.bookmaker}, probabilità {p.probabilities[sel]:.0%}, valore {o.value:+.1%}, {kind}"))  # fmt: skip
        if not found:
            return "Nessuna quota con valore nei prossimi 4 giorni sui bookmaker dell'utente."
        return "\n".join(t for _, t in sorted(found, reverse=True)[:15])

    def notizie_squadra(squadra: str) -> str:
        teams = find_teams(squadra)
        if not teams:
            return f"Nessuna squadra trovata con '{squadra}'."
        since = datetime.now(UTC) - FACTS_WINDOW
        lines = []
        for t in teams:
            facts = db.scalars(select(TeamFact).where(TeamFact.team_id == t.id, TeamFact.published_at >= since).order_by(TeamFact.published_at.desc()).limit(12)).all()
            lines.append(f"{t.name}: " + ("; ".join(f"[{f.published_at:%d/%m}] {KIND_LABELS.get(f.kind, f.kind)}{f' ({f.player})' if f.player else ''}: {f.detail}" for f in facts)
                                          or "nessuna notizia rilevante negli ultimi 10 giorni"))  # fmt: skip
        return "\n".join(lines)

    def le_mie_giocate() -> str:
        bets = db.scalars(select(Bet).where(Bet.user_id == user_id).order_by(Bet.placed_at.desc())).all()
        if not bets:
            return "L'utente non ha ancora registrato giocate."
        lines = []
        for kind, label in (("real", "Reali"), ("simulated", "Simulate")):
            s = summarize([b for b in bets if b.kind == kind])
            if s.bets:
                lines.append(f"{label}: {s.bets} schedine ({s.open} aperte), vinte {s.won}/{s.settled}, giocato {s.staked} €, tornato {s.returned} €, "
                             f"saldo {s.profit} €, rendimento {'n.d.' if s.roi is None else f'{s.roi:+.1%}'}, CLV medio {'n.d.' if s.avg_clv is None else f'{s.avg_clv:+.1%}'}")  # fmt: skip
        for b in bets[:8]:
            legs = ", ".join(f"{sel.match.home_team.name}-{sel.match.away_team.name} {(MARKET_NAMES.get(sel.market) or market_name(sel.market))} {sel.pick} @{sel.odds}" for sel in b.selections)
            lines.append(f"  {b.placed_at:%d/%m} {b.kind} {b.stake} € quota {b.total_odds:.2f} [{b.status}]: {legs}")
        return "\n".join(lines)

    return [
        Tool("cerca_partite", "Trova una squadra per nome e le sue prossime e ultime partite, con l'id da usare negli altri strumenti.",
             {"squadra": "Nome (o parte del nome) della squadra, es. 'Bari'"}, cerca_partite),
        Tool("scheda_partita", "Scheda completa di una partita: studio di Archie con i pronostici per livello e i loro motivi, classifica, forma, statistiche, probabilità e quote, "
             "notizie, tiri/angoli/cartellini attesi e tiratori.", {"match_id": "Id della partita (da cerca_partite)"}, scheda_partita, ("match_id",)),
        Tool("occasioni", "Le quote con valore dei prossimi 4 giorni sui bookmaker dell'utente (Sisal, Eurobet).", {}, occasioni),
        Tool("notizie_squadra", "Fatti recenti dalle notizie su una squadra: assenti, squalifiche, allenatore, società.",
             {"squadra": "Nome della squadra"}, notizie_squadra),
        Tool("le_mie_giocate", "Riepilogo delle giocate dell'utente: saldo, rendimento, CLV e ultime schedine.", {}, le_mie_giocate),
    ]  # fmt: skip


@router.get("")
def history(user: CurrentUser, db: DbSession, match_id: int | None = None) -> list[AnswerOut]:
    query = select(AiQuestion).where(AiQuestion.user_id == user.id)
    if match_id is not None:
        query = query.where(AiQuestion.match_id == match_id)
    return [_out(q) for q in db.scalars(query.order_by(AiQuestion.created_at.desc()).limit(20))]


@router.post("")
def ask_archie(body: AskIn, user: AdminUser, db: DbSession) -> AnswerOut:  # AI: solo l'amministratore
    from app.ai import ask as ask_module
    from app.ai.client import Ai, AiError
    from app.ai.gateway import BudgetExceeded

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(503, "Chiave Claude non configurata")
    context = ""
    if body.match_id is not None:
        match = db.get(Match, body.match_id)
        if match is None:
            raise HTTPException(404, "Partita non trovata")
        context = f"la domanda è fatta dalla pagina della partita id {match.id}: {match.home_team.name} - {match.away_team.name}, {_when(match)}."
    previous = db.scalars(select(AiQuestion).where(AiQuestion.user_id == user.id, AiQuestion.match_id == body.match_id)
                          .order_by(AiQuestion.created_at.desc()).limit(HISTORY)).all()  # fmt: skip
    try:
        answer = ask_module.ask(Ai(db, settings.anthropic_api_key, settings), settings.ai_model, body.question, build_tools(db, user.id), context,
                                user_id=user.id, history=[(q.question, q.answer) for q in reversed(previous)])  # fmt: skip
    except BudgetExceeded as exc:
        raise HTTPException(503, str(exc)) from exc
    except AiError as exc:
        raise HTTPException(502, f"Archie non è riuscito a rispondere: {exc}") from exc
    row = AiQuestion(user_id=user.id, match_id=body.match_id, question=body.question, answer=answer, created_at=datetime.now(UTC))
    db.add(row)
    db.commit()
    return _out(row)
