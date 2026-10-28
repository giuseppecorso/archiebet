"""Notifiche sul telefono (D158): chiave pubblica, attiva e spegni per questo dispositivo."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import CurrentUser, DbSession
from app.models import PushSubscription
from app.notify.push import public_key

router = APIRouter(prefix="/api/push", tags=["push"])


class Keys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=1000, pattern=r"^https://")
    keys: Keys


class EndpointIn(BaseModel):
    endpoint: str = Field(max_length=1000)


@router.get("/key")
def key(_: CurrentUser) -> dict[str, str]:
    return {"key": public_key()}


@router.post("/subscribe", status_code=204)
def subscribe(body: SubscriptionIn, user: CurrentUser, db: DbSession) -> None:
    """Questo dispositivo riceve le notifiche (se c'era già, ora è di questo utente)."""
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)) or PushSubscription(endpoint=body.endpoint)
    row.user_id, row.p256dh, row.auth = user.id, body.keys.p256dh, body.keys.auth
    db.add(row)
    db.commit()


@router.post("/unsubscribe", status_code=204)
def unsubscribe(body: EndpointIn, user: CurrentUser, db: DbSession) -> None:
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id))
    if row is not None:
        db.delete(row)
        db.commit()


@router.post("/status")
def status(body: EndpointIn, user: CurrentUser, db: DbSession) -> dict[str, bool]:
    """Questo dispositivo è attivo per questo utente?"""
    found = db.scalar(select(PushSubscription.id).where(PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id))
    return {"active": found is not None}
