from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.config import get_settings

app = FastAPI(title="ArchieBet", version="0.1.0")
app.include_router(auth_router)


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "env": get_settings().app_env}
