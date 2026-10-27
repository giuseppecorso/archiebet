"""Regolamento personale e stile di gioco (Fase 6, D114)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import CurrentUser, DbSession
from app.betting.rules import KINDS, DraftSelection, Rule, describe, suggest, violations
from app.config import get_settings
from app.models import Bet, Match, Team, UserRule, UserSettings

router = APIRouter(prefix="/api/rules", tags=["regolamento"])

STYLE_FRESH = timedelta(hours=24)


class RuleOut(BaseModel):
    id: int | None  # None = suggerimento non ancora accettato
    kind: str
    value: str
    text: str
    reason: str
    source: str
    active: bool


class RulesOut(BaseModel):
    rules: list[RuleOut]
    suggestions: list[RuleOut]
    style: str | None
    style_at: datetime | None


class RuleIn(BaseModel):
    kind: str
    value: str = Field("", max_length=40)
    reason: str = Field("", max_length=300)
    source: str = "mine"


class ActiveIn(BaseModel):
    active: bool


class DraftIn(BaseModel):
    stake: Decimal = Field(gt=0)
    selections: list[dict]  # {match_id, market, pick, odds}


class CheckOut(BaseModel):
    warnings: list[str]


def _team_names(db, rules) -> dict[int, str]:
    ids = [int(r.value) for r in rules if r.kind == "avoid_team" and r.value.isdigit()]
    return {t.id: t.name for t in db.scalars(select(Team).where(Team.id.in_(ids)))} if ids else {}


def _active_rules(db, user_id: int) -> list[Rule]:
    rules = [Rule(r.kind, r.value, r.reason) for r in db.scalars(select(UserRule).where(UserRule.user_id == user_id, UserRule.active.is_(True)))]
    settings = db.get(UserSettings, user_id)
    if settings and settings.favorite_team_id and not any(r.kind == "avoid_team" and r.value == str(settings.favorite_team_id) for r in rules):
        rules.append(Rule("avoid_team", str(settings.favorite_team_id), "squadra del cuore (Impostazioni)"))
    return rules


@router.get("")
def get_rules(user: CurrentUser, db: DbSession) -> RulesOut:
    stored = list(db.scalars(select(UserRule).where(UserRule.user_id == user.id).order_by(UserRule.created_at)))
    bets = list(db.scalars(select(Bet).where(Bet.user_id == user.id)))
    have = {(r.kind, r.value) for r in stored}
    sugg = [s for s in suggest(bets) if (s.kind, s.value) not in have]
    names = _team_names(db, [Rule(r.kind, r.value) for r in stored])
    settings = db.get(UserSettings, user.id)
    return RulesOut(
        rules=[RuleOut(id=r.id, kind=r.kind, value=r.value, text=describe(Rule(r.kind, r.value), names), reason=r.reason, source=r.source, active=r.active) for r in stored],
        suggestions=[RuleOut(id=None, kind=s.kind, value=s.value, text=describe(s), reason=s.reason, source="archie", active=False) for s in sugg],
        style=settings.style_text if settings else None,
        style_at=settings.style_at if settings else None,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def add_rule(body: RuleIn, user: CurrentUser, db: DbSession) -> RuleOut:
    if body.kind not in KINDS:
        raise HTTPException(422, "Tipo di regola sconosciuto")
    numeric = body.kind in ("max_legs", "max_total_odds", "max_stake", "avoid_team")
    try:
        if numeric and float(body.value) <= 0:
            raise ValueError
    except ValueError:
        raise HTTPException(422, "Serve un numero maggiore di zero") from None
    rule = UserRule(user_id=user.id, kind=body.kind, value=body.value.strip(), reason=body.reason, source="archie" if body.source == "archie" else "mine")
    db.add(rule)
    db.commit()
    return RuleOut(id=rule.id, kind=rule.kind, value=rule.value, text=describe(Rule(rule.kind, rule.value), _team_names(db, [Rule(rule.kind, rule.value)])),
                   reason=rule.reason, source=rule.source, active=True)  # fmt: skip


def _own(db, user_id: int, rule_id: int) -> UserRule:
    rule = db.get(UserRule, rule_id)
    if rule is None or rule.user_id != user_id:
        raise HTTPException(404, "Regola non trovata")
    return rule


@router.patch("/{rule_id}")
def toggle_rule(rule_id: int, body: ActiveIn, user: CurrentUser, db: DbSession) -> dict:
    _own(db, user.id, rule_id).active = body.active
    db.commit()
    return {"ok": True}


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, user: CurrentUser, db: DbSession) -> None:
    db.delete(_own(db, user.id, rule_id))
    db.commit()


@router.post("/check")
def check_draft(body: DraftIn, user: CurrentUser, db: DbSession) -> CheckOut:
    """Avvisi del regolamento per una schedina prima di registrarla (mai blocchi)."""
    from app.forecast.picks_service import match_market_picks

    rules = _active_rules(db, user.id)
    if not rules:
        return CheckOut(warnings=[])
    drafts = []
    for s in body.selections:
        match = db.get(Match, int(s.get("match_id", 0)))
        if match is not None:
            drafts.append(DraftSelection(match, str(s.get("market")), str(s.get("pick")), float(s.get("odds") or 0)))
    probs: dict[int, dict] = {}

    def value_of(d: DraftSelection) -> float | None:
        if d.match.id not in probs:
            probs[d.match.id] = {p.market: p.probabilities for p in match_market_picks(db, d.match, get_settings().radar_bookmaker_list)}
        p = probs[d.match.id].get(d.market, {}).get(d.pick)
        return p * d.odds - 1 if p and d.odds > 1 else None

    return CheckOut(warnings=violations(rules, body.stake, drafts, value_of, _team_names(db, rules)))


STYLE_SYSTEM = """Sei Archie. Scrivi "Il tuo stile di gioco" per l'utente in italiano semplice: 4-6 frasi, sincere e utili, come un amico esperto.
Usa SOLO i numeri della scheda (non inventarne). Di' cosa fa bene (dove il CLV è positivo) e cosa gli costa (dove il CLV o il
rendimento sono negativi con abbastanza giocate); se le giocate sono poche, dillo e non trarre conclusioni forti. Ricorda che
il giudice è il CLV, non i soldi vinti nel breve. Niente toni da venditore, niente inviti a giocare di più."""


@router.post("/style")
def write_style(user: CurrentUser, db: DbSession) -> RulesOut:
    from app.ai.client import Ai, AiError
    from app.ai.gateway import BudgetExceeded
    from app.betting.analysis import breakdown

    settings = get_settings()
    row = db.get(UserSettings, user.id)
    if row is None:
        row = UserSettings(user_id=user.id)
        db.add(row)
    now = datetime.now(UTC)
    if not (row.style_at and now - row.style_at < STYLE_FRESH):
        bets = list(db.scalars(select(Bet).where(Bet.user_id == user.id)))
        if not bets:
            raise HTTPException(422, "Registra qualche giocata: lo stile si scrive dai tuoi dati")
        if not settings.anthropic_api_key:
            raise HTTPException(503, "Chiave Claude non configurata")
        b = breakdown(bets)
        h = b.habits

        def groups(title, gs, sel=False):
            rows = []
            for g in gs:
                if sel:
                    rows.append(f"{g.label}: {g.selections} selezioni, vinte {g.won}, quota media {g.avg_odds or 0:.2f}, CLV medio "
                                f"{'n.d.' if g.avg_clv is None else f'{g.avg_clv:+.1%}'} ({g.clv_count} con CLV)")  # fmt: skip
                else:
                    rows.append(f"{g.label}: {g.bets} schedine, vinte {g.won}, giocato {g.staked} €, saldo {g.profit} €, rendimento {'n.d.' if g.roi is None else f'{g.roi:+.0%}'}")
            return f"{title}:\n" + "\n".join(f"- {r}" for r in rows)

        brief = "\n\n".join([
            f"Abitudini: {h.bets} schedine, puntata media {h.avg_stake} €, quota media {h.avg_odds or 0:.2f}, multiple {(h.multiple_share or 0):.0%}, "
            f"partite per schedina {h.avg_selections or 0:.1f}, mercato preferito {h.top_market}, bookmaker preferito {h.top_bookmaker}, "
            f"squadre più giocate {', '.join(f'{t} ({n})' for t, n in h.top_teams)}.",
            groups("Per numero di partite", b.by_size), groups("Per mercato", b.by_market, True), groups("Per campionato", b.by_competition, True),
        ])  # fmt: skip

        class Style(BaseModel):
            text: str

        try:
            out = Ai(db, settings.anthropic_api_key, settings).parse("style", settings.ai_model, STYLE_SYSTEM, brief, Style, user_id=user.id, effort="medium")
        except BudgetExceeded as exc:
            raise HTTPException(503, str(exc)) from exc
        except AiError as exc:
            raise HTTPException(502, f"Non riuscito: {exc}") from exc
        row.style_text, row.style_at = out.text, now
        db.commit()
    return get_rules(user, db)
