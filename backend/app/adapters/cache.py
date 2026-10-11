"""Cache su file per le risposte delle fonti dati: una cartella per fonte, un file JSON per richiesta."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

MISSING = object()


class FileCache:
    def __init__(self, root: Path, source: str, now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.dir = root / source
        self._now = now

    def _path(self, key: str) -> Path:
        return self.dir / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"

    def get(self, key: str, max_age: timedelta) -> Any:
        """Il dato salvato, oppure MISSING se non c'è o è più vecchio di max_age."""
        path = self._path(key)
        if not path.exists():
            return MISSING
        entry = json.loads(path.read_text(encoding="utf-8"))
        if self._now() - datetime.fromisoformat(entry["saved_at"]) > max_age:
            return MISSING
        return entry["data"]

    def set(self, key: str, data: Any) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        entry = {"key": key, "saved_at": self._now().isoformat(), "data": data}
        self._path(key).write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
