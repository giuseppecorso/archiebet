"""Tabelle del database.

Regola di scalabilità (sezione 14.2), da rispettare in ogni nuova tabella:
- dati PER UTENTE (giocate, schedine, impostazioni, limiti, regolamento): hanno sempre user_id;
- dati PER PARTITA (partite, quote, probabilità, mercati, contenuti AI per partita): niente user_id,
  si calcolano una volta sola e tutti gli utenti li leggono.
"""

from app.models.assistant import AiQuestion
from app.models.base import Base
from app.models.betting import Bet, BetKind, BetSelection, BetSnapshot, ChallengePick, UserRule, UserSettings
from app.models.forecast import MatchPrediction, RadarSignal
from app.models.sync import SyncRun
from app.models.news import MatchAnalysis, MatchInsight, NewsItem, TeamFact
from app.models.football import Competition, Match, MatchLive, MatchOdds, MatchSource, MatchStatus, Team, TeamAlias
from app.models.usage import UsageEvent
from app.models.user import User, UserSession

__all__ = [
    "AiQuestion",
    "Base",
    "Bet",
    "BetKind",
    "BetSelection",
    "BetSnapshot",
    "ChallengePick",
    "Competition",
    "Match",
    "MatchAnalysis",
    "MatchInsight",
    "MatchLive",
    "MatchOdds",
    "MatchPrediction",
    "MatchSource",
    "MatchStatus",
    "NewsItem",
    "RadarSignal",
    "SyncRun",
    "Team",
    "TeamFact",
    "TeamAlias",
    "UsageEvent",
    "UserRule",
    "UserSettings",
    "User",
    "UserSession",
]
