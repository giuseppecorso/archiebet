"""Freno ai tentativi di login (l'app è raggiungibile da internet con Tailscale Funnel, D150).

Dopo MAX_FAILURES password sbagliate per lo stesso nome utente, quel nome resta bloccato per LOCK.
In memoria: basta un solo processo, e un riavvio azzera i contatori (non è un problema per 6 utenti).
"""

import threading
from datetime import UTC, datetime, timedelta

MAX_FAILURES = 5
LOCK = timedelta(minutes=15)


class LoginLimiter:
    def __init__(self) -> None:
        self._failures: dict[str, list[datetime]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: datetime) -> list[datetime]:
        return [t for t in self._failures.get(key, []) if now - t < LOCK]

    def blocked(self, username: str, now: datetime | None = None) -> bool:
        with self._lock:
            return len(self._recent(username.strip().lower(), now or datetime.now(UTC))) >= MAX_FAILURES

    def failed(self, username: str, now: datetime | None = None) -> None:
        key, now = username.strip().lower(), now or datetime.now(UTC)
        with self._lock:
            self._failures[key] = [*self._recent(key, now), now]

    def succeeded(self, username: str) -> None:
        with self._lock:
            self._failures.pop(username.strip().lower(), None)


limiter = LoginLimiter()
