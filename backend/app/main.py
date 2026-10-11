import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.football import router as football_router
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


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "env": get_settings().app_env}
