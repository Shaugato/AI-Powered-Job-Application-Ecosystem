from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas.runtime import DocumentRuntimeStatus
from backend.app.services.document_runtime import DocumentRuntimeBootstrapService

router = APIRouter(tags=["runtime"])


@router.get("/runtime/document-intelligence", response_model=DocumentRuntimeStatus)
def document_intelligence_runtime_status() -> DocumentRuntimeStatus:
    service = DocumentRuntimeBootstrapService()
    report = service.status()
    return DocumentRuntimeStatus(**report)
