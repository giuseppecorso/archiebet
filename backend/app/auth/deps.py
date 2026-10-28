from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.service import user_from_token
from app.config import get_settings
from app.db import get_db
from app.models import User

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: DbSession) -> User:
    token = request.cookies.get(get_settings().session_cookie_name)
    user = user_from_token(db, token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Accesso richiesto")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_admin_user(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo l'amministratore")
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]


def get_premium_user(user: CurrentUser) -> User:
    """Funzioni Premium (D159): prova di 15 giorni, poi mesi riscattati o pagati. Finché gli abbonamenti non sono attivi, tutti."""
    from datetime import UTC, datetime

    from app.betting.coins import premium_until

    if not get_settings().subscriptions_enabled or user.is_admin:
        return user
    if premium_until(user.created_at, user.premium_paid_until) < datetime.now(UTC):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Funzione Premium: la prova gratuita è finita")
    return user


PremiumUser = Annotated[User, Depends(get_premium_user)]
