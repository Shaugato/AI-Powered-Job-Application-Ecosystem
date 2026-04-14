from fastapi import APIRouter, Depends, HTTPException
from typing import Any
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import NormalizedJobPosting
from backend.app.schemas.jobs import NormalizedJobPostingCreate, NormalizedJobPostingRead, OpportunityFitRead, SourceHealth
from backend.app.services.jobs import JobService
from backend.app.services.orchestration import OrchestrationService
from backend.app.services.retrieval import RetrievalService
from backend.app.services.source_registry import SourceRegistry

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[NormalizedJobPostingRead])
def list_jobs(db: Session = Depends(get_db)) -> list[NormalizedJobPosting]:
    return db.query(NormalizedJobPosting).order_by(NormalizedJobPosting.created_at.desc()).all()


@router.get("/sources/health", response_model=list[SourceHealth])
def source_health() -> list[SourceHealth]:
    registry = SourceRegistry.default()
    return [connector.health() for connector in registry.connectors.values()]


@router.get("/{job_id}", response_model=NormalizedJobPostingRead)
def get_job(job_id: str, db: Session = Depends(get_db)) -> NormalizedJobPosting:
    record = db.query(NormalizedJobPosting).filter(NormalizedJobPosting.id == job_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return record


@router.get("/{job_id}/fit", response_model=OpportunityFitRead)
def get_job_fit(job_id: str, db: Session = Depends(get_db)) -> OpportunityFitRead:
    job = db.query(NormalizedJobPosting).filter(NormalizedJobPosting.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    fit_result = RetrievalService(db).build_opportunity_fit(job)
    return OpportunityFitRead(
        job_id=job.id,
        fit_score=fit_result.fit.fit_score,
        component_scores=dict(fit_result.fit.component_scores_json or {}),
        matched_section_ids=list(fit_result.fit.matched_section_ids_json or []),
        missing_signals=list(fit_result.fit.missing_signals_json or []),
        explanations=list(fit_result.fit.explanation_json or []),
        requirement_profile=fit_result.requirement_profile,
        rerank_scores=list(fit_result.fit.rerank_scores_json or []),
        evidence_pack=list(fit_result.evidence_pack or []),
    )


@router.post("", response_model=NormalizedJobPostingRead)
def upsert_job(payload: NormalizedJobPostingCreate, db: Session = Depends(get_db)) -> NormalizedJobPosting:
    service = JobService(db)
    return service.upsert_job(payload)


@router.post("/{job_id}/pipeline")
async def start_job_pipeline(job_id: str) -> dict[str, Any]:
    result = await OrchestrationService().start_job_pipeline(job_id)
    return {"mode": result.mode, "workflow_id": result.workflow_id, "status": result.status, "details": result.details}


@router.put("/{job_id}", response_model=NormalizedJobPostingRead)
def update_job(job_id: str, payload: NormalizedJobPostingCreate, db: Session = Depends(get_db)) -> NormalizedJobPosting:
    service = JobService(db)
    record = service.update_job(job_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return record


@router.delete("/{job_id}")
def delete_job(job_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    record = db.query(NormalizedJobPosting).filter(NormalizedJobPosting.id == job_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(record)
    db.commit()
    return {"status": "deleted", "id": job_id}
