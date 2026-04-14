from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from temporalio.client import Client

from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.models.entities import EvidenceFragment, TruthStatus
from backend.app.schemas.corpus import (
    CorpusDocumentSummaryRead,
    CorpusIngestRequest,
    CorpusIngestResponse,
    CorpusIngestWorkflowResponse,
    CorpusLegacyCleanupResponse,
    EvidenceFragmentRead,
    SourceDocumentApprovalRequest,
    SourceDocumentApprovalResponse,
    TruthApprovalRequest,
)
from backend.app.schemas.profile_memory import CandidateMemoryRead, CandidateMemorySyncRequest
from backend.app.services.corpus import CorpusIngestionService
from backend.app.services.profile_memory import ProfileMemoryService
from backend.app.workflows.pipelines import DocumentIngestionWorkflow

router = APIRouter(prefix="/corpus", tags=["corpus"])


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned or "upload"


async def _run_ingestion_workflow(payload: CorpusIngestRequest) -> CorpusIngestResponse:
    settings = get_settings()
    client = await Client.connect(settings.temporal_target, namespace=settings.temporal_namespace)
    workflow_id = f"document-ingest-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    await client.start_workflow(
        DocumentIngestionWorkflow.run,
        payload.model_dump(),
        id=workflow_id,
        task_queue=settings.temporal_main_task_queue,
    )
    return CorpusIngestWorkflowResponse(accepted=True, workflow_id=workflow_id, workflow_status="running")


async def _read_ingestion_workflow(workflow_id: str) -> CorpusIngestWorkflowResponse:
    settings = get_settings()
    client = await Client.connect(settings.temporal_target, namespace=settings.temporal_namespace)
    handle = client.get_workflow_handle(workflow_id)
    try:
        description = await handle.describe()
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {type(exc).__name__}: {exc}") from exc
    workflow_status = str(getattr(description.status, "name", description.status)).lower()
    response = CorpusIngestWorkflowResponse(accepted=True, workflow_id=workflow_id, workflow_status=workflow_status)
    if workflow_status == "completed":
        response.result = CorpusIngestResponse(**await handle.result())
    elif workflow_status in {"failed", "terminated", "canceled", "timed_out"}:
        try:
            await handle.result()
        except Exception as exc:
            response.error = f"{type(exc).__name__}: {exc}"
    return response


@router.post("/ingest", response_model=CorpusIngestWorkflowResponse)
async def ingest_corpus(payload: CorpusIngestRequest, db: Session = Depends(get_db)) -> CorpusIngestWorkflowResponse:
    try:
        return await _run_ingestion_workflow(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        service = CorpusIngestionService(db)
        try:
            return CorpusIngestWorkflowResponse(
                accepted=True,
                workflow_id=f"synchronous-ingest-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
                workflow_status="completed",
                result=service.ingest_directory(payload),
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/upload", response_model=CorpusIngestWorkflowResponse)
async def upload_corpus_files(
    files: list[UploadFile] = File(...),
    collection_name: str = Form("manual-upload"),
    role_hint: str = Form(""),
    document_kind: str = Form("auto"),
    db: Session = Depends(get_db),
) -> CorpusIngestWorkflowResponse:
    settings = get_settings()
    target_dir = settings.corpus_upload_dir / _safe_segment(collection_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    for upload in files:
        original_name = Path(upload.filename or "document.txt").name
        safe_name = _safe_segment(Path(original_name).stem)
        suffix = "".join(Path(original_name).suffixes)
        destination = target_dir / f"{safe_name}{suffix}"
        contents = await upload.read()
        destination.write_bytes(contents)

    payload = CorpusIngestRequest(
        path=str(target_dir),
        role_hint=[item.strip() for item in role_hint.split(",") if item.strip()],
        source_document_glob="**/*",
        document_kind_override=None if document_kind == "auto" else document_kind,
    )
    try:
        return await _run_ingestion_workflow(payload)
    except Exception:
        return CorpusIngestWorkflowResponse(
            accepted=True,
            workflow_id=f"synchronous-upload-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            workflow_status="completed",
            result=CorpusIngestionService(db).ingest_directory(payload),
        )


@router.get("/workflows/{workflow_id}", response_model=CorpusIngestWorkflowResponse)
async def get_ingestion_workflow(workflow_id: str) -> CorpusIngestWorkflowResponse:
    return await _read_ingestion_workflow(workflow_id)


@router.get("/memory", response_model=CandidateMemoryRead)
def get_candidate_memory(profile_id: str | None = None, db: Session = Depends(get_db)) -> CandidateMemoryRead:
    return ProfileMemoryService(db).build_memory(profile_id=profile_id)


@router.post("/memory/sync")
def sync_candidate_memory(payload: CandidateMemorySyncRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    profile = ProfileMemoryService(db).sync_to_profile(profile_id=payload.profile_id, overwrite_summary=payload.overwrite_summary)
    if profile is None:
        raise HTTPException(status_code=404, detail="Base profile not found")
    return {"status": "synced", "profile_id": profile.id}


@router.get("/library", response_model=list[CorpusDocumentSummaryRead])
def list_corpus_library(db: Session = Depends(get_db)) -> list[CorpusDocumentSummaryRead]:
    return CorpusIngestionService(db).list_document_summaries()


@router.post("/cleanup-legacy", response_model=CorpusLegacyCleanupResponse)
def cleanup_legacy_bad_uploads(db: Session = Depends(get_db)) -> CorpusLegacyCleanupResponse:
    return CorpusIngestionService(db).cleanup_legacy_bad_uploads()


@router.get("/evidence", response_model=list[EvidenceFragmentRead])
def list_evidence(truth_status: TruthStatus | None = None, db: Session = Depends(get_db)) -> list[EvidenceFragment]:
    query = db.query(EvidenceFragment).order_by(EvidenceFragment.created_at.desc())
    if truth_status is not None:
        query = query.filter(EvidenceFragment.truth_status == truth_status)
    return query.all()


@router.post("/evidence/{fragment_id}/approve", response_model=EvidenceFragmentRead)
def approve_fragment(fragment_id: str, payload: TruthApprovalRequest, db: Session = Depends(get_db)) -> EvidenceFragment:
    fragment = db.query(EvidenceFragment).filter(EvidenceFragment.id == fragment_id).first()
    if fragment is None:
        raise HTTPException(status_code=404, detail="Evidence fragment not found")
    fragment.truth_status = TruthStatus.APPROVED if payload.approved else TruthStatus.REJECTED
    metadata = fragment.metadata_json or {}
    if payload.reviewer_notes:
        metadata["reviewer_notes"] = payload.reviewer_notes
    fragment.metadata_json = metadata
    db.add(fragment)
    db.commit()
    db.refresh(fragment)
    return fragment


@router.post("/documents/approve", response_model=SourceDocumentApprovalResponse)
def approve_source_document(payload: SourceDocumentApprovalRequest, db: Session = Depends(get_db)) -> SourceDocumentApprovalResponse:
    try:
        return CorpusIngestionService(db).approve_source_document(
            source_document=payload.source_document,
            approved=payload.approved,
            reviewer_notes=payload.reviewer_notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
