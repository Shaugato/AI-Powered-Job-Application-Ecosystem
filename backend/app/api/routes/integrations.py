from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.integrations import (
    IntegrationBrowserCaptureRead,
    IntegrationConnectResponse,
    IntegrationConnectionCreate,
    IntegrationConnectionRead,
    IntegrationProviderRead,
)
from backend.app.services.integrations import IntegrationService

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/providers", response_model=list[IntegrationProviderRead])
def list_providers(category: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[IntegrationProviderRead]:
    return IntegrationService(db).list_providers(category=category)


@router.get("/connections", response_model=list[IntegrationConnectionRead])
def list_connections(db: Session = Depends(get_db)) -> list[IntegrationConnectionRead]:
    return IntegrationService(db).list_connections()


@router.post("/connections", response_model=IntegrationConnectionRead)
def create_connection(payload: IntegrationConnectionCreate, db: Session = Depends(get_db)) -> IntegrationConnectionRead:
    return IntegrationService(db).create_connection(payload)


@router.put("/connections/{connection_id}", response_model=IntegrationConnectionRead)
def update_connection(connection_id: str, payload: IntegrationConnectionCreate, db: Session = Depends(get_db)) -> IntegrationConnectionRead:
    record = IntegrationService(db).update_connection(connection_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return record


@router.delete("/connections/{connection_id}")
def delete_connection(connection_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    deleted = IntegrationService(db).delete_connection(connection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return {"status": "deleted", "id": connection_id}


@router.post("/connections/{connection_id}/connect", response_model=IntegrationConnectResponse)
def connect_connection(connection_id: str, db: Session = Depends(get_db)) -> IntegrationConnectResponse:
    response = IntegrationService(db).connect(connection_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return response


@router.get("/connections/{connection_id}/browser-capture", response_model=IntegrationBrowserCaptureRead)
def get_browser_capture(connection_id: str, db: Session = Depends(get_db)) -> IntegrationBrowserCaptureRead:
    try:
        response = IntegrationService(db).browser_capture_status(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return response


@router.post("/connections/{connection_id}/browser-capture/finalize", response_model=IntegrationBrowserCaptureRead)
def finalize_browser_capture(connection_id: str, db: Session = Depends(get_db)) -> IntegrationBrowserCaptureRead:
    try:
        response = IntegrationService(db).finalize_browser_capture(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return response


@router.post("/connections/{connection_id}/browser-capture/cancel", response_model=IntegrationBrowserCaptureRead)
def cancel_browser_capture(connection_id: str, db: Session = Depends(get_db)) -> IntegrationBrowserCaptureRead:
    try:
        response = IntegrationService(db).cancel_browser_capture(connection_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if response is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return response


@router.post("/connections/{connection_id}/session-state", response_model=IntegrationConnectionRead)
async def upload_session_state(connection_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)) -> IntegrationConnectionRead:
    if FilePath(file.filename or "session.json").suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="Session state upload must be a JSON file")
    contents = await file.read()
    try:
        record = IntegrationService(db).save_browser_session_state(connection_id, filename=file.filename or "storage_state.json", payload=contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return record


@router.get("/oauth/callback/{provider_key}", response_class=HTMLResponse)
def oauth_callback(provider_key: str, code: str | None = None, state: str | None = None, db: Session = Depends(get_db)) -> HTMLResponse:
    if not code:
        return HTMLResponse("<html><body><h3>Missing authorization code.</h3></body></html>", status_code=400)
    record = IntegrationService(db).handle_oauth_callback(provider_key, code=code, state=state)
    if record is None:
        return HTMLResponse("<html><body><h3>Connection could not be completed.</h3></body></html>", status_code=400)
    return HTMLResponse(f"<html><body><h3>{record.name} connected.</h3><p>Status: {record.status}</p><p>You can return to the dashboard now.</p></body></html>")

