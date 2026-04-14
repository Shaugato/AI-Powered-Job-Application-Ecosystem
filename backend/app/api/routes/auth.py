from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.auth import AuthStatusRead
from backend.app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()


@router.get("/status", response_model=AuthStatusRead)
def auth_status(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> AuthStatusRead:
    token = _extract_token(authorization)
    return AuthService(db).auth_status(token)


@router.get("/google/start")
def google_start(next_url: str | None = Query(default=None), db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        auth_url = AuthService(db).google_start_url(next_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(auth_url, status_code=302)


@router.get("/google/callback")
def google_callback(code: str | None = None, state: str | None = None, db: Session = Depends(get_db)) -> RedirectResponse:
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")
    try:
        result = AuthService(db).complete_google_login(code, state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(result.redirect_url, status_code=302)


@router.post("/logout")
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict[str, object]:
    token = _extract_token(authorization)
    logged_out = AuthService(db).logout(token)
    return {"status": "logged_out" if logged_out else "no_session"}
