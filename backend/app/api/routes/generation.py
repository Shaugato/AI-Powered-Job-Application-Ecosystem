from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from temporalio.client import Client

from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.models.entities import GenerationResult, ResumeCompositionPlan, TemplateVariant
from backend.app.schemas.generation import (
    GenerationRequestCreate,
    GenerationResultRead,
    GenerationWorkflowResponse,
    TemplateVariantCreate,
    TemplateVariantRead,
)
from backend.app.services.generation import GenerationService
from backend.app.workflows.pipelines import GenerationWorkflow

router = APIRouter(prefix="/generation", tags=["generation"])


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned or "template"


def _upsert_template(db: Session, *, name: str, document_kind: str, template_path: str, metadata_json: dict | None) -> TemplateVariant:
    template = db.query(TemplateVariant).filter(TemplateVariant.name == name).first()
    if template is None:
        template = TemplateVariant(
            name=name,
            document_kind=document_kind,
            template_path=template_path,
            metadata_json=metadata_json,
        )
    else:
        template.document_kind = document_kind
        template.template_path = template_path
        template.metadata_json = metadata_json

    db.add(template)
    db.commit()
    db.refresh(template)
    return template


async def _run_generation_workflow(payload: GenerationRequestCreate) -> GenerationWorkflowResponse:
    settings = get_settings()
    client = await Client.connect(settings.temporal_target, namespace=settings.temporal_namespace)
    workflow_id = f"generation-request-{payload.job_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    await client.start_workflow(
        GenerationWorkflow.run,
        payload.model_dump(),
        id=workflow_id,
        task_queue=settings.temporal_main_task_queue,
    )
    return GenerationWorkflowResponse(accepted=True, workflow_id=workflow_id, workflow_status="running")


async def _read_generation_workflow(workflow_id: str, db: Session) -> GenerationWorkflowResponse:
    settings = get_settings()
    client = await Client.connect(settings.temporal_target, namespace=settings.temporal_namespace)
    handle = client.get_workflow_handle(workflow_id)
    try:
        description = await handle.describe()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {type(exc).__name__}: {exc}") from exc
    workflow_status = str(getattr(description.status, "name", description.status)).lower()
    response = GenerationWorkflowResponse(accepted=True, workflow_id=workflow_id, workflow_status=workflow_status)
    if workflow_status == "completed":
        workflow_result = await handle.result()
        generation_result_id = str((workflow_result or {}).get("generation_result_id") or "")
        if generation_result_id:
            result = db.query(GenerationResult).filter(GenerationResult.id == generation_result_id).first()
            if result is not None:
                response.result = _serialize_result(db, result)
    elif workflow_status in {"failed", "terminated", "canceled", "timed_out"}:
        try:
            await handle.result()
        except Exception as exc:
            response.error = f"{type(exc).__name__}: {exc}"
    return response


def _serialize_result(db: Session, result: GenerationResult) -> GenerationResultRead:
    plan = None
    if result.composition_plan_id:
        plan = db.query(ResumeCompositionPlan).filter(ResumeCompositionPlan.id == result.composition_plan_id).first()
    metadata = dict(plan.metadata_json or {}) if plan else {}
    return GenerationResultRead(
        id=result.id,
        request_id=result.request_id,
        composition_plan_id=result.composition_plan_id,
        resume_json=dict(result.resume_json or {}),
        cover_letter_json=dict(result.cover_letter_json or {}),
        qa_scores_json=dict(result.qa_scores_json or {}),
        compile_status=result.compile_status,
        resume_tex_path=result.resume_tex_path,
        resume_pdf_path=result.resume_pdf_path,
        cover_tex_path=result.cover_tex_path,
        cover_pdf_path=result.cover_pdf_path,
        preview_html_path=result.preview_html_path,
        preview_pdf_path=result.preview_pdf_path,
        selected_section_ids_json=list(result.selected_section_ids_json or []),
        excluded_section_ids_json=list(result.excluded_section_ids_json or []),
        fit_score=float(result.fit_score or 0.0),
        verifier_output_json=dict(result.verifier_output_json or {}),
        repair_attempts_json=list(result.repair_attempts_json or []),
        stage_status_json=dict(result.stage_status_json or {}),
        composition_plan_json=dict(plan.composition_json or {}) if plan else {},
        evidence_pack_json=list(plan.evidence_pack_json or []) if plan else [],
        layout_blueprint_json=dict(plan.layout_blueprint_json or {}) if plan else {},
        rendered_metrics_json=dict(plan.rendered_metrics_json or {}) if plan else {},
        verification_json=dict(plan.verification_json or {}) if plan else {},
        rewrite_provenance_json=dict(metadata.get("rewrite_provenance") or {}),
        grounding_notes=result.grounding_notes,
    )


@router.get("/results", response_model=list[GenerationResultRead])
def list_generation_results(db: Session = Depends(get_db)) -> list[GenerationResultRead]:
    results = db.query(GenerationResult).order_by(GenerationResult.created_at.desc()).all()
    return [_serialize_result(db, result) for result in results]


@router.get("/results/{generation_result_id}", response_model=GenerationResultRead)
def get_generation_result(generation_result_id: str, db: Session = Depends(get_db)) -> GenerationResultRead:
    result = db.query(GenerationResult).filter(GenerationResult.id == generation_result_id).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Generation result not found")
    return _serialize_result(db, result)


@router.get("/templates", response_model=list[TemplateVariantRead])
def list_templates(db: Session = Depends(get_db)) -> list[TemplateVariant]:
    return db.query(TemplateVariant).order_by(TemplateVariant.name.asc()).all()


@router.get("/templates/{template_id}", response_model=TemplateVariantRead)
def get_template(template_id: str, db: Session = Depends(get_db)) -> TemplateVariant:
    template = db.query(TemplateVariant).filter(TemplateVariant.id == template_id).first()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("/templates", response_model=TemplateVariantRead)
def create_or_update_template(payload: TemplateVariantCreate, db: Session = Depends(get_db)) -> TemplateVariant:
    return _upsert_template(
        db,
        name=payload.name,
        document_kind=payload.document_kind,
        template_path=payload.template_path,
        metadata_json=payload.metadata_json,
    )


@router.put("/templates/{template_id}", response_model=TemplateVariantRead)
def update_template(template_id: str, payload: TemplateVariantCreate, db: Session = Depends(get_db)) -> TemplateVariant:
    template = db.query(TemplateVariant).filter(TemplateVariant.id == template_id).first()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    template.name = payload.name
    template.document_kind = payload.document_kind
    template.template_path = payload.template_path
    template.metadata_json = payload.metadata_json
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/templates/{template_id}")
def delete_template(template_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    template = db.query(TemplateVariant).filter(TemplateVariant.id == template_id).first()
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    db.delete(template)
    db.commit()
    return {"status": "deleted", "id": template_id}


@router.post("/templates/upload", response_model=TemplateVariantRead)
async def upload_template(
    file: UploadFile = File(...),
    name: str = Form(...),
    document_kind: str = Form(...),
    db: Session = Depends(get_db),
) -> TemplateVariant:
    settings = get_settings()
    original_name = Path(file.filename or "template.tex.j2").name
    safe_stem = _safe_segment(Path(original_name).stem)
    suffix = "".join(Path(original_name).suffixes) or ".tex.j2"
    destination = settings.template_upload_dir / f"{safe_stem}{suffix}"
    destination.write_bytes(await file.read())

    metadata = {
        "uploaded": True,
        "original_filename": original_name,
        "supports_jinja": destination.suffix == ".j2" or destination.name.endswith(".tex.j2"),
    }
    return _upsert_template(
        db,
        name=name,
        document_kind=document_kind,
        template_path=str(destination),
        metadata_json=metadata,
    )


@router.post("/requests", response_model=GenerationWorkflowResponse)
async def create_generation_request(payload: GenerationRequestCreate, db: Session = Depends(get_db)) -> GenerationWorkflowResponse:
    try:
        return await _run_generation_workflow(payload)
    except Exception:
        pass
    service = GenerationService(db)
    try:
        result = service.generate(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Generation failed: {type(exc).__name__}: {exc}") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return GenerationWorkflowResponse(
        accepted=True,
        workflow_id=f"synchronous-generation-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        workflow_status="completed",
        result=_serialize_result(db, result),
    )


@router.get("/workflows/{workflow_id}", response_model=GenerationWorkflowResponse)
async def get_generation_workflow(workflow_id: str, db: Session = Depends(get_db)) -> GenerationWorkflowResponse:
    return await _read_generation_workflow(workflow_id, db)
