from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import GenerationResult, SubmissionPreview
from backend.app.schemas.artifacts import ArtifactDescriptor, GenerationArtifactBundle
from backend.app.services.generation import GenerationService

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/generation-results/{generation_result_id}", response_model=GenerationArtifactBundle)
def list_generation_artifacts(generation_result_id: str, db: Session = Depends(get_db)) -> GenerationArtifactBundle:
    result = db.query(GenerationResult).filter(GenerationResult.id == generation_result_id).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Generation result not found")
    preview = db.query(SubmissionPreview).filter(SubmissionPreview.generation_result_id == generation_result_id).first()
    artifacts = [
        ArtifactDescriptor(
            kind="resume_preview",
            label="Resume Preview",
            available=bool(result.preview_html_path or result.resume_json),
            filename=Path(result.preview_html_path).name if result.preview_html_path else "resume_preview.html",
            url=f"/api/v1/artifacts/generation-results/{generation_result_id}/resume_preview",
        ),
        ArtifactDescriptor(
            kind="resume_pdf",
            label="Resume PDF",
            available=bool(result.preview_pdf_path or result.resume_pdf_path),
            filename=Path(result.preview_pdf_path or result.resume_pdf_path).name if (result.preview_pdf_path or result.resume_pdf_path) else None,
            url=f"/api/v1/artifacts/generation-results/{generation_result_id}/resume_pdf" if (result.preview_pdf_path or result.resume_pdf_path) else None,
        ),
        ArtifactDescriptor(
            kind="cover_text",
            label="Cover Letter",
            available=bool(result.cover_letter_json),
            filename="cover_letter.json",
            url=f"/api/v1/artifacts/generation-results/{generation_result_id}/cover_text" if result.cover_letter_json else None,
        ),
    ]
    if preview and preview.pdf_path:
        artifacts.append(
            ArtifactDescriptor(
                kind="application_preview_pdf",
                label="Application Preview PDF",
                available=True,
                filename=Path(preview.pdf_path).name,
                url=f"/api/v1/artifacts/generation-results/{generation_result_id}/application_preview_pdf",
            )
        )
    return GenerationArtifactBundle(generation_result_id=generation_result_id, artifacts=artifacts)


@router.get("/generation-results/{generation_result_id}/{artifact_kind}")
def download_generation_artifact(generation_result_id: str, artifact_kind: str, db: Session = Depends(get_db)):
    result = db.query(GenerationResult).filter(GenerationResult.id == generation_result_id).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Generation result not found")
    preview = db.query(SubmissionPreview).filter(SubmissionPreview.generation_result_id == generation_result_id).first()

    if artifact_kind == "resume_preview":
        html_path = Path(result.preview_html_path) if result.preview_html_path else None
        if html_path and html_path.exists():
            return HTMLResponse(html_path.read_text(encoding="utf-8"))
        return HTMLResponse(GenerationService.render_resume_preview_html(result.resume_json, job_title="Tailored role", company="Target company"))

    if artifact_kind == "resume_pdf":
        pdf_path = Path(result.preview_pdf_path or result.resume_pdf_path or "")
        if pdf_path.exists():
            return FileResponse(path=pdf_path, filename=pdf_path.name, media_type="application/pdf")
        raise HTTPException(status_code=404, detail="PDF artifact missing")

    if artifact_kind == "application_preview_pdf":
        if preview and preview.pdf_path and Path(preview.pdf_path).exists():
            pdf_path = Path(preview.pdf_path)
            return FileResponse(path=pdf_path, filename=pdf_path.name, media_type="application/pdf")
        raise HTTPException(status_code=404, detail="Application preview PDF missing")

    if artifact_kind == "cover_text":
        return result.cover_letter_json

    raise HTTPException(status_code=404, detail="Artifact kind not found")
