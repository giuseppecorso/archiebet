from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.auth.deps import CurrentUser, DbSession
from app.auth.limiter import limiter
from app.auth.service import authenticate, close_session, open_session
from app.config import get_settings
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    is_admin: bool

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(id=user.id, username=user.username, is_admin=user.is_admin)


@router.post("/login")
def login(body: LoginRequest, response: Response, db: DbSession) -> UserOut:
    if limiter.blocked(body.username):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Troppi tentativi sbagliati: riprova tra 15 minuti")
    user = authenticate(db, body.username, body.password)
    if user is None:
        limiter.failed(body.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nome utente o password errati")
    limiter.succeeded(body.username)
    settings = get_settings()
    token = open_session(db, user, settings.session_days)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,  # JavaScript non può leggerlo
        secure=settings.cookie_secure,
        samesite="lax",  # non viene inviato da richieste partite da altri siti
    )
    return UserOut.of(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession) -> None:
    name = get_settings().session_cookie_name
    if token := request.cookies.get(name):
        close_session(db, token)
    response.delete_cookie(name)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.of(user)
