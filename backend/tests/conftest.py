import os

# I test non toccano mai il database vero
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SYNC_ENABLED"] = "false"  # nessun download durante i test

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import get_db, make_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture
def db() -> Session:
    # StaticPool: una sola connessione condivisa, altrimenti ogni connessione vedrebbe un DB vuoto
    engine = make_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def logged_client(client: TestClient, db: Session) -> TestClient:
    from app.auth.service import create_user

    create_user(db, "giuse", "una-password-lunga", is_admin=True)  # Giuse è l'amministratore
    assert client.post("/api/auth/login", json={"username": "giuse", "password": "una-password-lunga"}).status_code == 200
    return client
