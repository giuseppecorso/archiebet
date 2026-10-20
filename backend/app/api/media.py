"""Stemmi delle squadre e loghi dei campionati (D84).

Le immagini arrivano da API-Football (media.api-sports.io, non consumano richieste del piano) e si salvano
sul PC al primo uso: l'app non richiama il sito a ogni pagina. Uso privato (principio 6).
"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.adapters.api_football import LEAGUES
from app.auth.deps import CurrentUser, DbSession
from app.config import get_settings
from app.models import TeamAlias

router = APIRouter(prefix="/api/media", tags=["immagini"])

MEDIA_URL = "https://media.api-sports.io/football/{kind}/{id}.png"
ONE_MONTH = "public, max-age=2592000"  # il browser le tiene un mese


def media_file(kind: str, external_id: int, download=None) -> Path | None:
    """Percorso dell'immagine salvata; la scarica se manca. None se API-Football non ce l'ha."""
    folder = Path(get_settings().data_cache_dir) / "media" / kind
    path = folder / f"{external_id}.png"
    if path.exists():
        return path if path.stat().st_size else None  # file vuoto = "non esiste", non si riprova
    content = (download or _download)(MEDIA_URL.format(kind=kind, id=external_id))
    folder.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content or b"")
    return path if content else None


@router.get("/team/{team_id}.png")
def team_logo(team_id: int, _: CurrentUser, db: DbSession) -> FileResponse:
    alias = db.scalar(
        select(TeamAlias.alias).where(TeamAlias.team_id == team_id, TeamAlias.source == "api-football").limit(1)
    )
    if alias is None or not re.fullmatch(r"\d+", alias):
        raise HTTPException(404, "stemma non disponibile")
    return _respond(media_file("teams", int(alias)))


@router.get("/competition/{code}.png")
def competition_logo(code: str, _: CurrentUser) -> FileResponse:
    league = next((league for league, c in LEAGUES.items() if c == code), None)
    if league is None:
        raise HTTPException(404, "logo non disponibile")
    return _respond(media_file("leagues", league))


def _respond(path: Path | None) -> FileResponse:
    if path is None:
        raise HTTPException(404, "immagine non disponibile")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": ONE_MONTH})


def _download(url: str) -> bytes | None:
    import httpx2

    response = httpx2.get(url, timeout=20, follow_redirects=True)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content
