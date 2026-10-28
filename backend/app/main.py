import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.api.bets import router as bets_router
from app.api.football import router as football_router
from app.api.lab import router as lab_router
from app.api.status import router as status_router
from app.api.media import router as media_router
from app.api.ask import router as ask_router
from app.api.fan import router as fan_router
from app.api.play import router as play_router
from app.api.tv import router as tv_router
from app.api.rules import router as rules_router
from app.api.picks import router as picks_router
from app.api.radar import router as radar_router
from app.api.study import router as study_router
from app.api.daily import router as daily_router
from app.api.push import router as push_router
from app.api.coins import router as coins_router
from app.auth.router import router as auth_router
from app.config import get_settings
from app.jobs import start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler = start_scheduler(get_settings())
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="ArchieBet", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(football_router)
app.include_router(lab_router)
app.include_router(study_router)
app.include_router(daily_router)
app.include_router(push_router)
app.include_router(coins_router)
app.include_router(bets_router)
app.include_router(status_router)
app.include_router(radar_router)
app.include_router(picks_router)
app.include_router(media_router)
app.include_router(fan_router)
app.include_router(ask_router)
app.include_router(rules_router)
app.include_router(play_router)
app.include_router(tv_router)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "env": get_settings().app_env}


# --- App compilata sulla stessa porta dell'API (D150): niente server di sviluppo esposto a internet ---
_dist = Path(get_settings().frontend_dist).resolve() if get_settings().frontend_dist else None
if _dist is not None and (_dist / "index.html").is_file():

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "Non trovato")
        file = (_dist / path).resolve()
        fresh = {"Cache-Control": "no-cache"}  # la pagina si ricontrolla sempre: dopo un aggiornamento il telefono vede subito la versione nuova
        if path and file.is_file() and file.is_relative_to(_dist):  # solo file dentro la cartella dell'app
            return FileResponse(file, headers=None if file.name.startswith(("chunk-", "main-", "styles-", "polyfills-")) else fresh)
        return FileResponse(_dist / "index.html", headers=fresh)  # le pagine dell'app (es. /partite/12) le gestisce Angular
