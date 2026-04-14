from __future__ import annotations

from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from backend.app.db.session import SessionLocal
from backend.app.models.entities import GenerationResult, IngestionSourceConfig, NormalizedJobPosting
from backend.app.schemas.application import ApplicationPlanCreate
from backend.app.schemas.corpus import CorpusIngestRequest
from backend.app.schemas.generation import GenerationRequestCreate
from backend.app.services.application import ApplicationService
from backend.app.services.corpus import CorpusIngestionService
from backend.app.services.generation import GenerationService
from backend.app.services.ingestion import IngestionService
from backend.app.services.retrieval import RetrievalService
from backend.app.services.structured_memory import StructuredMemoryService


@activity.defn
async def document_ingestion_activity(payload: dict[str, Any]) -> dict[str, Any]:
    with SessionLocal() as db:
        try:
            result = CorpusIngestionService(db).ingest_directory(CorpusIngestRequest(**payload))
        except FileNotFoundError as exc:
            raise ApplicationError(str(exc), type="FileNotFoundError", non_retryable=True) from exc
        return result.model_dump()


@activity.defn
async def profile_fusion_activity() -> dict[str, Any]:
    with SessionLocal() as db:
        profile = StructuredMemoryService(db)._refresh_memory_profile()
        db.commit()
        return {"status": "completed", "profile_id": profile.id if profile else None}


@activity.defn
async def ingest_corpus_activity(path: str) -> dict[str, str]:
    return {"status": "queued", "path": path}


@activity.defn
async def discover_jobs_activity(config_id: str, workflow_id: str | None = None) -> dict[str, Any]:
    with SessionLocal() as db:
        config = db.query(IngestionSourceConfig).filter(IngestionSourceConfig.id == config_id).first()
        result = IngestionService(db).run_config_once(config_id, workflow_id=workflow_id)
        if result is None:
            return {"status": "failed", "config_id": config_id}
        return {
            "status": result.run.status.value,
            "config_id": config_id,
            "run_id": result.run.id,
            "pipeline_job_ids": result.pipeline_job_ids,
            "cadence_minutes": config.cadence_minutes if config is not None else 60,
        }


@activity.defn
async def job_understanding_activity(job_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        job = db.query(NormalizedJobPosting).filter(NormalizedJobPosting.id == job_id).first()
        if job is None:
            return {"status": "failed", "job_id": job_id}
        fit_result = RetrievalService(db).build_opportunity_fit(job)
        db.commit()
        return {
            "status": "completed",
            "job_id": job_id,
            "fit_id": fit_result.fit.id,
            "requirement_profile": fit_result.requirement_profile,
            "fit_score": fit_result.fit.fit_score,
        }


@activity.defn
async def evidence_pack_activity(job_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        job = db.query(NormalizedJobPosting).filter(NormalizedJobPosting.id == job_id).first()
        if job is None:
            return {"status": "failed", "job_id": job_id}
        fit_result = RetrievalService(db).build_opportunity_fit(job)
        db.commit()
        return {
            "status": "completed",
            "job_id": job_id,
            "fit_id": fit_result.fit.id,
            "evidence_pack": fit_result.evidence_pack,
            "matched_section_ids": fit_result.fit.matched_section_ids_json,
        }


@activity.defn
async def generate_documents_activity(payload: dict[str, Any]) -> dict[str, str]:
    request = GenerationRequestCreate(**payload)
    with SessionLocal() as db:
        result = GenerationService(db).generate(request)
        if result is None:
            return {"status": "failed", "job_id": request.job_id}
        return {"status": "completed", "job_id": request.job_id, "generation_result_id": result.id}


@activity.defn
async def resume_verification_activity(generation_result_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        result = db.query(GenerationResult).filter(GenerationResult.id == generation_result_id).first()
        if result is None:
            return {"status": "failed", "generation_result_id": generation_result_id}
        return {
            "status": "completed",
            "generation_result_id": generation_result_id,
            "verification": dict(result.verifier_output_json or {}),
            "repair_attempts": list(result.repair_attempts_json or []),
            "stage_status": dict(result.stage_status_json or {}),
        }


@activity.defn
async def render_and_repair_activity(generation_result_id: str) -> dict[str, Any]:
    with SessionLocal() as db:
        result = db.query(GenerationResult).filter(GenerationResult.id == generation_result_id).first()
        if result is None:
            return {"status": "failed", "generation_result_id": generation_result_id}
        return {
            "status": "completed",
            "generation_result_id": generation_result_id,
            "preview_html_path": result.preview_html_path,
            "preview_pdf_path": result.preview_pdf_path,
            "compile_status": result.compile_status,
        }


@activity.defn
async def create_application_plan_activity(job_id: str, generation_result_id: str) -> dict[str, str]:
    with SessionLocal() as db:
        result = ApplicationService(db).create_plan(
            ApplicationPlanCreate(job_id=job_id, generation_result_id=generation_result_id)
        )
        if result is None:
            return {"status": "failed", "job_id": job_id, "generation_result_id": generation_result_id}
        return {"status": "completed", "plan_id": result.id, "mode": result.mode.value}


@activity.defn
async def execute_application_activity(plan_id: str) -> dict[str, str]:
    with SessionLocal() as db:
        result = ApplicationService(db).start_run(plan_id)
        if result is None:
            return {"status": "failed", "plan_id": plan_id}
        return {"status": result.status.value, "plan_id": plan_id, "run_id": result.id}
