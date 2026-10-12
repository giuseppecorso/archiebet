"""Cassaforte: le stagioni dalla 2025/26 in poi non si usano per valutare o tarare il modello.

Servono per il verdetto finale (principio 3). Si aprono una volta sola, con il comando
`python -m app.cli open-vault`, che lascia un file con la data di apertura in `backend/data/`.
Il modello può comunque USARE quelle partite come storia per prevedere le successive: è vietato
solo misurarsi su di esse prima del verdetto.
"""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from app.config import BACKEND_DIR

VAULT_FIRST_SEASON = "2025/26"
VAULT_MARKER = BACKEND_DIR / "data" / "vault_opened.txt"


class VaultLockedError(Exception):
    pass


def is_vault_season(season: str) -> bool:
    return season >= VAULT_FIRST_SEASON  # "2024/25" < "2025/26" < "2026/27": l'ordine alfabetico basta


def vault_is_open(marker: Path = VAULT_MARKER) -> bool:
    return marker.exists()


def ensure_can_evaluate(seasons: Iterable[str], marker: Path = VAULT_MARKER) -> None:
    locked = sorted(s for s in set(seasons) if is_vault_season(s))
    if locked and not vault_is_open(marker):
        raise VaultLockedError(f"Stagioni in cassaforte, valutazione vietata fino al verdetto: {', '.join(locked)}")


def open_vault(now: datetime, marker: Path = VAULT_MARKER) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"Cassaforte aperta il {now.isoformat(timespec='seconds')}\n", encoding="utf-8")
