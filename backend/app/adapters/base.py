"""Base comune delle fonti dati (sezione 14.4).

Ogni fornitore (football-data, API-Football, OddsPapi, ...) avrà il suo modulo in app/adapters/
che eredita da DataSourceAdapter. Il resto del codice parla solo con gli adapter:
cambiare fornitore o piano non tocca altro.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Any, ClassVar

from app.adapters.cache import MISSING, FileCache


class DataSourceAdapter:
    source: ClassVar[str]  # nome della fonte, usato anche nel registro consumi

    def __init__(self, cache: FileCache, on_call: Callable[[str], None] | None = None):
        self.cache = cache
        self._on_call = on_call  # avvisato a ogni chiamata vera (non servita dalla cache)

    def cached(self, key: str, max_age: timedelta, fetch: Callable[[], Any]) -> Any:
        """Restituisce il dato dalla cache se abbastanza recente, altrimenti lo scarica e lo salva."""
        data = self.cache.get(key, max_age)
        if data is not MISSING:
            return data
        data = fetch()
        if self._on_call:
            self._on_call(self.source)
        self.cache.set(key, data)
        return data
