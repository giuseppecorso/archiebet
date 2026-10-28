from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    premium_paid_until: Mapped[datetime | None] = mapped_column(UTCDateTime)  # mesi riscattati con gli ArchieCoins o pagati (D159)


class UserSession(Base):
    """Sessione di login. Nel DB si salva solo l'impronta (hash) del token, mai il token."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class PushSubscription(Base):
    """Un dispositivo che riceve le notifiche (Web Push, D158): indirizzo del servizio push del browser e chiavi pubbliche."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CoinRedemption(Base):
    """ArchieCoins spesi (D159): per ora solo mesi di Premium."""

    __tablename__ = "coin_redemptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    coins: Mapped[int] = mapped_column()
    what: Mapped[str] = mapped_column(String(40))  # "premium-month"
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
