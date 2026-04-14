from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.entities import (
    GenerationRequest,
    GenerationResult,
    NormalizedJobPosting,
    PipelineEntityType,
    PipelineStageName,
    PromptVersion,
    ResumeCompositionPlan,
    ReviewQueueReason,
    SubmissionPreview,
    TemplateVariant,
)
from backend.app.schemas.generation import GenerationRequestCreate
from backend.app.services.learning import LearningService
from backend.app.services.pipeline_state import PipelineStateService
from backend.app.services.profile_memory import ProfileMemoryService
from backend.app.services.resume_builder import ResumeBuilder
from backend.app.services.review_queue import ReviewQueueService
from backend.app.services.retrieval import RetrievalService, classify_job_labels


class GenerationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.learning = LearningService(db)
        self.memory = ProfileMemoryService(db)
        self.retrieval = RetrievalService(db)
        self.builder = ResumeBuilder(db)
        self.pipeline_state = PipelineStateService(db)
        self.review_queue = ReviewQueueService(db)

    def generate(self, payload: GenerationRequestCreate) -> GenerationResult | None:
        job = self.db.query(NormalizedJobPosting).filter(NormalizedJobPosting.id == payload.job_id).first()
        if job is None:
            return None
        if not job.classification_labels_json:
            job.classification_labels_json = classify_job_labels(job.description_text, job.title)

        fit_result = self.retrieval.build_opportunity_fit(job)
        prompt = self.learning.select_prompt_for_job(job)
        resume_template = self._find_template(payload.template_variant_name)
        cover_template = self._find_template(payload.cover_template_variant_name)
        memory_snapshot = self.memory.build_memory().model_dump()

        request = GenerationRequest(
            job_id=job.id,
            prompt_version_id=prompt.id if prompt else None,
            template_variant_id=resume_template.id if resume_template else None,
            selected_evidence_ids_json=fit_result.fit.matched_section_ids_json,
            request_payload_json={
                "job_id": job.id,
                "template_variant_name": payload.template_variant_name,
                "cover_template_variant_name": payload.cover_template_variant_name,
                "force_regenerate": payload.force_regenerate,
                "fit_score": fit_result.fit.fit_score,
            },
            status="in_progress",
        )
        self.db.add(request)
        self.db.flush()

        self._record_stage(
            request_id=request.id,
            stage_name=PipelineStageName.JOB_UNDERSTANDING,
            stage_index=0,
            status="completed",
            payload={
                "job_id": job.id,
                "requirement_profile": fit_result.requirement_profile,
                "fit_score": fit_result.fit.fit_score,
                "explanations": list(fit_result.fit.explanation_json or []),
            },
            confidence=float(fit_result.fit.fit_score or 0.0),
            validation_result={"missing_signals": list(fit_result.fit.missing_signals_json or [])},
        )
        self._record_stage(
            request_id=request.id,
            stage_name=PipelineStageName.EVIDENCE_PACK,
            stage_index=1,
            status="completed",
            payload={
                "matched_section_ids": list(fit_result.fit.matched_section_ids_json or []),
                "evidence_pack": list(fit_result.evidence_pack or []),
            },
            confidence=float(fit_result.fit.fit_score or 0.0),
            validation_result={"evidence_pack_size": len(fit_result.evidence_pack or [])},
        )

        composed = self.builder.compose(job=job, fit_result=fit_result, memory_snapshot=memory_snapshot)
        resume = dict(composed["resume"])
        cover_letter = dict(composed["cover_letter"])
        evidence_pack = list(composed.get("evidence_pack") or [])
        layout_blueprint = dict(composed.get("layout_blueprint") or {})
        trim_decisions = list(composed.get("trim_decisions") or [])
        verification = dict(composed.get("verification") or {})
        repair_attempts = list(composed.get("repair_attempts") or [])
        rewrite_provenance = dict(composed.get("rewrite_provenance") or {})
        section_budget = dict(composed.get("section_budget") or {})

        self._record_stage(
            request_id=request.id,
            stage_name=PipelineStageName.TAILORING,
            stage_index=2,
            status="completed",
            payload={
                "selected_section_ids": list(composed.get("selected_section_ids") or []),
                "excluded_section_ids": list(composed.get("excluded_section_ids") or []),
                "rewrite_provenance": rewrite_provenance,
            },
            confidence=float(verification.get("confidence") or fit_result.fit.fit_score or 0.0),
            validation_result={"unsupported_claim_risk": [issue for issue in verification.get("issues") or [] if issue.get("code") == "unsupported_claims"]},
        )
        self._record_stage(
            request_id=request.id,
            stage_name=PipelineStageName.LAYOUT_PLANNING,
            stage_index=3,
            status="completed",
            payload=layout_blueprint,
            confidence=float(layout_blueprint.get("font_scale", 1.0)),
            validation_result={"line_budget": int(layout_blueprint.get("line_budget") or 52), "estimated_lines": int(layout_blueprint.get("estimated_lines") or 0)},
            repair_hints=[{"action": "trim", "detail": decision} for decision in trim_decisions],
        )

        artifact_dir = self.settings.artifacts_dir / "generated" / request.id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        preview_html_path, preview_pdf_path, rendered_metrics = self.builder.render_preview(
            artifact_dir=artifact_dir,
            resume=resume,
            job_title=job.title,
            company=job.company,
        )
        self.builder.update_page_plan(resume, layout_blueprint=layout_blueprint, decisions=trim_decisions, rendered_metrics=rendered_metrics)
        verification = self.builder.verify_resume(
            resume=resume,
            evidence_pack=evidence_pack,
            requirement_profile=fit_result.requirement_profile,
            rendered_metrics=rendered_metrics,
        )
        self._record_stage(
            request_id=request.id,
            stage_name=PipelineStageName.RENDER,
            stage_index=4,
            status="completed" if preview_html_path else "failed",
            payload={"preview_html_path": str(preview_html_path), "preview_pdf_path": str(preview_pdf_path) if preview_pdf_path else None, "metrics": rendered_metrics},
            confidence=1.0 if preview_pdf_path else 0.55,
            validation_result={"engine": rendered_metrics.get("engine")},
        )
        self._record_stage(
            request_id=request.id,
            stage_name=PipelineStageName.VERIFICATION,
            stage_index=5,
            status="completed" if verification.get("passed") else "needs_repair",
            payload=verification,
            confidence=float(verification.get("confidence") or 0.0),
            validation_result=dict(verification.get("checks") or {}),
            repair_hints=list(verification.get("repair_hints") or []),
        )

        final_needs_review = self._needs_review(verification, rendered_metrics)
        if final_needs_review:
            for attempt in range(self.settings.document_max_repair_attempts):
                repaired_resume, repair_record, repaired_layout_blueprint, planning_decisions = self.builder.repair_resume(
                    resume=resume,
                    verification=verification,
                    rendered_metrics=rendered_metrics,
                    requirement_profile=fit_result.requirement_profile,
                )
                if not repair_record.get("changed"):
                    break
                resume = repaired_resume
                layout_blueprint = repaired_layout_blueprint
                trim_decisions.extend(planning_decisions)
                preview_html_path, preview_pdf_path, rendered_metrics = self.builder.render_preview(
                    artifact_dir=artifact_dir,
                    resume=resume,
                    job_title=job.title,
                    company=job.company,
                )
                self.builder.update_page_plan(resume, layout_blueprint=layout_blueprint, decisions=trim_decisions, rendered_metrics=rendered_metrics)
                verification = self.builder.verify_resume(
                    resume=resume,
                    evidence_pack=evidence_pack,
                    requirement_profile=fit_result.requirement_profile,
                    rendered_metrics=rendered_metrics,
                )
                repair_attempt = {
                    "attempt": attempt + 1,
                    "repair": repair_record,
                    "verification": verification,
                    "rendered_metrics": rendered_metrics,
                }
                repair_attempts.append(repair_attempt)
                self._record_stage(
                    request_id=request.id,
                    stage_name=PipelineStageName.REPAIR,
                    stage_index=6,
                    status="applied",
                    payload=repair_attempt,
                    confidence=float(verification.get("confidence") or 0.0),
                    validation_result=dict(verification.get("checks") or {}),
                    repair_hints=list(verification.get("repair_hints") or []),
                )
                self._record_stage(
                    request_id=request.id,
                    stage_name=PipelineStageName.RENDER,
                    stage_index=4,
                    status="completed" if preview_html_path else "failed",
                    payload={"preview_html_path": str(preview_html_path), "preview_pdf_path": str(preview_pdf_path) if preview_pdf_path else None, "metrics": rendered_metrics},
                    confidence=1.0 if preview_pdf_path else 0.55,
                    validation_result={"engine": rendered_metrics.get("engine")},
                )
                self._record_stage(
                    request_id=request.id,
                    stage_name=PipelineStageName.VERIFICATION,
                    stage_index=5,
                    status="completed" if verification.get("passed") else "needs_repair",
                    payload=verification,
                    confidence=float(verification.get("confidence") or 0.0),
                    validation_result=dict(verification.get("checks") or {}),
                    repair_hints=list(verification.get("repair_hints") or []),
                )
                if not self._needs_review(verification, rendered_metrics):
                    break

        stage_status = {
            "job_understanding": "completed",
            "evidence_pack": "completed",
            "tailoring": "completed",
            "layout_planning": "completed",
            "verification": "completed" if verification.get("passed") else "needs_review",
            "render": "completed" if preview_html_path else "failed",
            "repair": "applied" if repair_attempts else "not_needed",
        }

        review_item = None
        final_needs_review = self._needs_review(verification, rendered_metrics)
        if final_needs_review:
            review_reason = ReviewQueueReason.REPAIR_EXHAUSTED if repair_attempts else ReviewQueueReason.VERIFIER_FAILURE
            review_item = self.review_queue.enqueue(
                reason=review_reason,
                summary="Tailored resume requires human review because the verifier still found unresolved issues after deterministic repair.",
                confidence=float(verification.get("confidence") or 0.0),
                details={
                    "verification": verification,
                    "rendered_metrics": rendered_metrics,
                    "repair_attempts": repair_attempts,
                    "job_id": job.id,
                    "request_id": request.id,
                },
                job_id=job.id,
                stage_name=PipelineStageName.VERIFICATION.value,
            )
            stage_status["review_queue"] = "open"
            request.status = "review_required"
            self._record_stage(
                request_id=request.id,
                stage_name=PipelineStageName.REPAIR,
                stage_index=6,
                status="review_required",
                payload={"review_queue_item_id": review_item.id, "verification": verification, "rendered_metrics": rendered_metrics},
                confidence=float(verification.get("confidence") or 0.0),
                validation_result=dict(verification.get("checks") or {}),
                repair_hints=list(verification.get("repair_hints") or []),
            )
        else:
            request.status = "completed"

        composition_plan = ResumeCompositionPlan(
            job_id=job.id,
            generation_request_id=request.id,
            profile_id=fit_result.fit.profile_id,
            fit_id=fit_result.fit.id,
            selected_section_ids_json=list(composed.get("selected_section_ids") or []),
            excluded_section_ids_json=list(composed.get("excluded_section_ids") or []),
            section_order_json=["identity", "summary", "technical_skills", "experience", "projects", "certifications", "education"],
            section_budget_json=section_budget,
            estimated_lines=int(resume.get("page_plan", {}).get("estimated_lines", 0)),
            line_budget=int(resume.get("page_plan", {}).get("line_budget", 52)),
            trim_decisions_json=self._dedupe(trim_decisions),
            evidence_pack_json=evidence_pack,
            layout_blueprint_json=layout_blueprint,
            rendered_metrics_json=rendered_metrics,
            verification_json=verification,
            repair_loop_json=repair_attempts,
            composition_json=resume,
            metadata_json={
                "fit_explanations": fit_result.fit.explanation_json,
                "requirement_profile": fit_result.requirement_profile,
                "rewrite_provenance": rewrite_provenance,
            },
        )
        self.db.add(composition_plan)
        self.db.flush()

        qa_scores = self._qa_scores(job.description_text, resume, fit_result.fit, verification, rendered_metrics)
        result = GenerationResult(
            request_id=request.id,
            composition_plan_id=composition_plan.id,
            resume_json=resume,
            cover_letter_json=cover_letter,
            qa_scores_json=qa_scores,
            compile_status="compiled" if preview_pdf_path else "html-only",
            resume_tex_path=None,
            resume_pdf_path=str(preview_pdf_path) if preview_pdf_path else None,
            cover_tex_path=None,
            cover_pdf_path=None,
            preview_html_path=str(preview_html_path),
            preview_pdf_path=str(preview_pdf_path) if preview_pdf_path else None,
            selected_section_ids_json=list(composed.get("selected_section_ids") or []),
            excluded_section_ids_json=list(composed.get("excluded_section_ids") or []),
            fit_score=fit_result.fit.fit_score,
            verifier_output_json=verification,
            repair_attempts_json=repair_attempts,
            stage_status_json=stage_status,
            grounding_notes=self._grounding_notes(
                selected_section_count=len(composed.get("selected_section_ids") or []),
                fit_explanations=list(fit_result.fit.explanation_json or []),
                trim_decisions=self._dedupe(trim_decisions),
                verification=verification,
            ),
        )
        self.db.add(result)
        self.db.flush()

        if review_item is not None:
            review_item.generation_result_id = result.id
            self.db.add(review_item)

        preview = SubmissionPreview(
            generation_result_id=result.id,
            html_path=str(preview_html_path),
            pdf_path=str(preview_pdf_path) if preview_pdf_path else None,
            preview_required=True,
            selected_section_ids_json=list(composed.get("selected_section_ids") or []),
            composition_snapshot_json=resume,
            verification_metadata_json={
                "verification": verification,
                "repair_attempts": repair_attempts,
                "layout_blueprint": layout_blueprint,
                "rendered_metrics": rendered_metrics,
                "review_queue_item_id": review_item.id if review_item else None,
            },
            metadata_json={"job_id": job.id, "company": job.company, "title": job.title},
        )
        self.db.add(preview)

        if prompt is not None:
            prompt.last_used_at = datetime.now(timezone.utc)
            self.db.add(prompt)

        self.db.add(request)
        self.db.commit()
        self.db.refresh(result)
        self.learning.upsert_resume_variant_score(result.id)
        return result

    def _record_stage(
        self,
        *,
        request_id: str,
        stage_name: PipelineStageName,
        stage_index: int,
        status: str,
        payload: dict[str, Any],
        confidence: float,
        validation_result: dict[str, Any] | None = None,
        repair_hints: list[dict[str, Any]] | None = None,
    ) -> None:
        self.pipeline_state.record_stage(
            entity_type=PipelineEntityType.GENERATION,
            entity_id=request_id,
            stage_name=stage_name,
            stage_index=stage_index,
            status=status,
            payload=payload,
            confidence=confidence,
            provenance=[{"engine": "generation_service"}],
            validation_result=validation_result or {},
            repair_hints=repair_hints or [],
        )

    def _needs_review(self, verification: dict[str, Any], rendered_metrics: dict[str, Any]) -> bool:
        if not verification.get("passed"):
            return True
        return int(rendered_metrics.get("estimated_pages") or 1) > 1 or int(rendered_metrics.get("overflow_px") or 0) > 0

    def _find_template(self, name: str) -> TemplateVariant | None:
        return self.db.query(TemplateVariant).filter(TemplateVariant.name == name).first()

    def _qa_scores(self, job_description: str, resume: dict[str, Any], fit, verification: dict[str, Any], rendered_metrics: dict[str, Any]) -> dict[str, Any]:
        job_tokens = set(job_description.lower().split())
        generated_tokens = set(json.dumps(resume).lower().split())
        component_scores = dict(fit.component_scores_json or {})
        return {
            "keyword_coverage": round(len(job_tokens & generated_tokens) / max(len(job_tokens), 1), 3),
            "fit_score": float(fit.fit_score),
            "semantic_match": float(component_scores.get("semantic") or 0.0),
            "lexical_match": float(component_scores.get("lexical") or 0.0),
            "missing_signals": list(fit.missing_signals_json or []),
            "estimated_lines": float(resume.get("page_plan", {}).get("estimated_lines", 0)),
            "rendered_pages": int(rendered_metrics.get("estimated_pages") or 1),
            "overflow_px": int(rendered_metrics.get("overflow_px") or 0),
            "verifier_confidence": float(verification.get("confidence") or 0.0),
        }

    def _grounding_notes(self, *, selected_section_count: int, fit_explanations: list[str], trim_decisions: list[str], verification: dict[str, Any]) -> str:
        parts = [
            f"Generated from {selected_section_count} canonical memory sections using retrieve-rerank evidence selection.",
            *fit_explanations[:3],
            *trim_decisions[:4],
        ]
        if verification.get("issues"):
            parts.append(f"Verifier flagged {len(verification.get('issues') or [])} issue(s) for review-aware handling.")
        return " ".join(part for part in parts if part).strip()

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result

    @staticmethod
    def render_resume_preview_html(resume: dict[str, Any], *, job_title: str, company: str) -> str:
        return ResumeBuilder.render_resume_preview_html(resume, job_title=job_title, company=company)
