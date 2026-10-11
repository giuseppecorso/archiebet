"""Tabelle del database.

Regola di scalabilità (sezione 14.2), da rispettare in ogni nuova tabella:
- dati PER UTENTE (giocate, schedine, impostazioni, limiti, regolamento): hanno sempre user_id;
- dati PER PARTITA (partite, quote, probabilità, mercati, contenuti AI per partita): niente user_id,
  si calcolano una volta sola e tutti gli utenti li leggono.
"""

from app.models.base import Base
from app.models.usage import UsageEvent
from app.models.user import User, UserSession

__all__ = ["Base", "UsageEvent", "User", "UserSession"]
