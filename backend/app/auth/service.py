from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password, hash_token, new_session_token, verify_password
from app.models import User, UserSession
from app.models.base import utcnow


MAX_USERS = 6  # l'amministratore e al massimo 5 amici (anche il limite gratuito di Tailscale)


def create_user(db: Session, username: str, password: str, is_admin: bool = False) -> User:
    username = username.strip().lower()
    if not username:
        raise ValueError("Il nome utente non può essere vuoto")
    if len(db.scalars(select(User.id)).all()) >= MAX_USERS:
        raise ValueError(f"Ci sono già {MAX_USERS} utenti: l'amministratore e 5 amici al massimo")
    if db.scalar(select(User).where(User.username == username)):
        raise ValueError(f"L'utente '{username}' esiste già")
    user = User(username=username, password_hash=hash_password(password), is_admin=is_admin)
    db.add(user)
    db.commit()
    return user


def set_password(db: Session, username: str, password: str) -> User:
    """Cambia la password e chiude tutte le sessioni aperte dell'utente."""
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None:
        raise ValueError(f"L'utente '{username}' non esiste")
    user.password_hash = hash_password(password)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if not verify_password(password, user.password_hash if user else None):
        return None
    return user


def open_session(db: Session, user: User, days: int) -> str:
    """Crea una sessione e restituisce il token da mettere nel cookie."""
    token = new_session_token()
    now = utcnow()
    db.add(UserSession(user_id=user.id, token_hash=hash_token(token), created_at=now, expires_at=now + timedelta(days=days)))
    # Pulizia delle sessioni scadute dell'utente
    db.execute(delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at < now))
    db.commit()
    return token


def user_from_token(db: Session, token: str) -> User | None:
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if session is None or session.expires_at <= utcnow():
        return None
    return db.get(User, session.user_id)


def close_session(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
    db.commit()
