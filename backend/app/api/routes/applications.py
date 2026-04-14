from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import ApplicationPlan, ApplicationRun, SubmissionPreview
from backend.app.schemas.application import (
    ApplicationPlanCreate,
    ApplicationPlanRead,
    ApplicationPreviewRead,
    ApplicationRunRead,
    ApplicationRunStartRequest,
)
from backend.app.services.application import ApplicationService

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("/plans", response_model=list[ApplicationPlanRead])
def list_application_plans(db: Session = Depends(get_db)) -> list[ApplicationPlan]:
    return db.query(ApplicationPlan).order_by(ApplicationPlan.created_at.desc()).all()


@router.post("/plans", response_model=ApplicationPlanRead)
def create_application_plan(payload: ApplicationPlanCreate, db: Session = Depends(get_db)) -> ApplicationPlan:
    service = ApplicationService(db)
    plan = service.create_plan(payload)
    if plan is None:
        raise HTTPException(status_code=404, detail="Missing job or generation result")
    return plan


@router.get("/runs", response_model=list[ApplicationRunRead])
def list_application_runs(db: Session = Depends(get_db)) -> list[ApplicationRun]:
    return db.query(ApplicationRun).order_by(ApplicationRun.created_at.desc()).all()


@router.post("/runs", response_model=ApplicationRunRead)
def start_application_run(payload: ApplicationRunStartRequest, db: Session = Depends(get_db)) -> ApplicationRun:
    service = ApplicationService(db)
    run = service.start_run(payload.plan_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Application plan not found")
    return run


def _load_preview(application_plan_id: str, db: Session) -> tuple[ApplicationPlan, SubmissionPreview]:
    plan = db.query(ApplicationPlan).filter(ApplicationPlan.id == application_plan_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Application plan not found")
    preview = db.query(SubmissionPreview).filter(SubmissionPreview.application_plan_id == plan.id).first()
    if preview is None:
        raise HTTPException(status_code=404, detail="Preview not available")
    return plan, preview


@router.get("/{application_plan_id}/preview-metadata", response_model=ApplicationPreviewRead)
def get_application_preview_metadata(application_plan_id: str, db: Session = Depends(get_db)) -> ApplicationPreviewRead:
    plan, preview = _load_preview(application_plan_id, db)
    return ApplicationPreviewRead(
        application_plan_id=plan.id,
        generation_result_id=preview.generation_result_id,
        html_path=preview.html_path,
        pdf_path=preview.pdf_path,
        preview_required=preview.preview_required,
        selected_section_ids_json=list(preview.selected_section_ids_json or []),
        composition_snapshot_json=dict(preview.composition_snapshot_json or {}),
        verification_metadata_json=dict(preview.verification_metadata_json or {}),
        metadata_json=dict(preview.metadata_json or {}),
    )


@router.get("/{application_plan_id}/preview")
def get_application_preview(application_plan_id: str, db: Session = Depends(get_db)):
    _, preview = _load_preview(application_plan_id, db)
    html_path = Path(preview.html_path) if preview.html_path else None
    if html_path and html_path.exists():
        return HTMLResponse(html_path.read_text(encoding="utf-8"))
    pdf_path = Path(preview.pdf_path) if preview.pdf_path else None
    if pdf_path and pdf_path.exists():
        return FileResponse(path=pdf_path, filename=pdf_path.name, media_type="application/pdf")
    raise HTTPException(status_code=404, detail="Preview artifact missing")
