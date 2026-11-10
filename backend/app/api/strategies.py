"""Scheda Strategie (D189): le strategie famose del mercato messe alla prova sull'archivio.

I numeri li calcola `python -m app.cli market-strategies` e li salva accanto al modulo: l'archivio non cambia,
quindi non serve ricalcolarli a ogni richiesta.
"""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter

from app.auth.deps import CurrentUser
from app.forecast import market_strategies

router = APIRouter(prefix="/api/strategies", tags=["strategie"])

RESULTS = Path(market_strategies.__file__).with_suffix(".json")


@lru_cache(maxsize=1)
def _load(path: Path, mtime: float) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_results(path: Path = RESULTS) -> dict:
    """Il risultato salvato, o un elenco vuoto se la prova non è ancora stata fatta."""
    if not path.exists():
        return {"generated_at": None, "strategies": []}
    return _load(path, path.stat().st_mtime)


@router.get("")
def market_strategies_results(_: CurrentUser) -> dict:
    return load_results()
