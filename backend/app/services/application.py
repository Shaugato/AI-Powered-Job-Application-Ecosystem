from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.entities import (
    ApplicationMode,
    ApplicationPlan,
    ApplicationRun,
    ApplicationStatus,
    BaseProfile,
    GenerationResult,
    NormalizedJobPosting,
    RunStatus,
    SubmissionPreview,
)
from backend.app.schemas.application import ApplicationPlanCreate
from backend.app.services.integrations import IntegrationService
from backend.app.services.notifications import NotificationService
from backend.app.services.source_registry import SourceRegistry


AUTHENTICATED_APPLICATION_SOURCES = {"linkedin", "seek", "indeed"}


def plan_mode_for_job(
    *,
    source: str,
    risk_flags: list[str],
    auto_submit_certified: bool,
    profile_ready: bool,
    requires_authenticated_account: bool,
    connection_ready: bool,
) -> tuple[ApplicationMode, list[str], str]:
    reasons: list[str] = []
    if source == "linkedin":
        reasons.append("LinkedIn is restricted to review-before-apply in v1")
        return ApplicationMode.REVIEW_REQUIRED, reasons, "review_before_apply"
    if source in {"apsjobs", "careers_vic"}:
        reasons.append("Government portals require manual review")
        return ApplicationMode.REVIEW_REQUIRED, reasons, "review_before_apply"
    if any(flag in {"essay_required", "legal_declaration", "merit_criteria"} for flag in risk_flags):
        reasons.append("High-friction application fields detected")
        return ApplicationMode.REVIEW_REQUIRED, reasons, "review_before_apply"
    if requires_authenticated_account and not connection_ready:
        reasons.append("A connected account session is required before this source can be auto-submitted")
        return ApplicationMode.REVIEW_REQUIRED, reasons, "review_before_apply"
    if not profile_ready:
        reasons.append("Base profile is incomplete for deterministic submission")
        return ApplicationMode.REVIEW_REQUIRED, reasons, "review_before_apply"
    if not auto_submit_certified:
        reasons.append("Connector is not certified for auto-submit")
        return ApplicationMode.REVIEW_REQUIRED, reasons, "review_before_apply"
    return ApplicationMode.AUTO_SUBMIT, reasons, "certified_autopilot"


class ApplicationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.registry = SourceRegistry.default()
        self.notifications = NotificationService(db)
        self.integrations = IntegrationService(db)

    def create_plan(self, payload: ApplicationPlanCreate) -> ApplicationPlan | None:
        job = self.db.query(NormalizedJobPosting).filter(NormalizedJobPosting.id == payload.job_id).first()
        result = self.db.query(GenerationResult).filter(GenerationResult.id == payload.generation_result_id).first()
        if job is None or result is None:
            return None

        profile = self.db.query(BaseProfile).order_by(BaseProfile.created_at.desc()).first()
        profile_ready = bool(profile and profile.full_name and profile.email)
        connector = self.registry.get(job.source.value)
        job_metadata = job.metadata_json or {}
        preferred_connection_id = job_metadata.get("application_connection_id") or job_metadata.get("connection_id")
        connection = self.integrations.connection_for_source(job.source.value, preferred_connection_id=preferred_connection_id, purpose="application")
        connection_runtime = self.integrations.connection_runtime_payload(connection)
        requires_authenticated_account = job.source.value in AUTHENTICATED_APPLICATION_SOURCES
        connection_ready = bool(connection_runtime.get("has_session_state")) if requires_authenticated_account else True
        mode, reasons, source_policy = plan_mode_for_job(
            source=job.source.value,
            risk_flags=job.risk_flags_json,
            auto_submit_certified=connector.auto_submit_certified,
            profile_ready=profile_ready,
            requires_authenticated_account=requires_authenticated_account,
            connection_ready=connection_ready,
        )
        verifier_output = dict(result.verifier_output_json or {})
        render_metrics = dict((result.resume_json or {}).get('page_plan', {}).get('rendered_metrics') or {})
        generation_requires_review = (
            not bool(verifier_output.get('passed'))
            or str((result.stage_status_json or {}).get('review_queue') or '').lower() == 'open'
            or int(render_metrics.get('estimated_pages') or 1) > 1
            or int(render_metrics.get('overflow_px') or 0) > 0
            or not bool(result.preview_pdf_path)
        )
        if generation_requires_review:
            reasons = [*reasons, 'Generated resume failed verifier or overflow checks and requires review before submission']
            mode = ApplicationMode.REVIEW_REQUIRED
            source_policy = 'verification_review'
        preview = self.db.query(SubmissionPreview).filter(SubmissionPreview.generation_result_id == result.id).first()
        field_map = {
            "target_url": job.source_url,
            "resume_path": result.preview_pdf_path or result.resume_pdf_path or result.preview_html_path,
            "resume_preview_path": result.preview_html_path,
            "cover_letter_text": result.cover_letter_json.get("opening") if result.cover_letter_json else "",
            "full_name": profile.full_name if profile else "",
            "email": profile.email if profile else "",
            "phone": profile.phone if profile else "",
            "location": profile.location if profile else "",
            "website": profile.website if profile else "",
            "summary": profile.summary if profile else "",
            "job_title": job.title,
            "company": job.company,
            "allow_auto_submit": mode == ApplicationMode.AUTO_SUBMIT and not generation_requires_review,
            "requires_authenticated_account": requires_authenticated_account,
            **connection_runtime,
        }
        plan = ApplicationPlan(
            job_id=job.id,
            generation_result_id=result.id,
            source_adapter=connector.source_name,
            mode=mode,
            field_map_json=field_map,
            risk_reasons_json=reasons,
            fit_reasons_json=list((job.metadata_json or {}).get("requirement_profile", {}).get("required_skills") or []),
            approval_state="required" if mode != ApplicationMode.AUTO_SUBMIT else "not_required",
            notification_state="queued",
            preview_required=mode != ApplicationMode.AUTO_SUBMIT or generation_requires_review,
            source_policy=source_policy,
            fit_score=float(result.fit_score or 0.0),
            terminal_status=ApplicationStatus.REVIEW_REQUIRED if mode != ApplicationMode.AUTO_SUBMIT or generation_requires_review else ApplicationStatus.PLANNED,
        )
        self.db.add(plan)
        self.db.flush()
        if preview:
            preview.application_plan_id = plan.id
            preview.preview_required = mode != ApplicationMode.AUTO_SUBMIT or generation_requires_review
            self.db.add(preview)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def start_run(self, plan_id: str) -> ApplicationRun | None:
        plan = self.db.query(ApplicationPlan).filter(ApplicationPlan.id == plan_id).first()
        if plan is None:
            return None

        connector = self.registry.get(plan.source_adapter)
        if plan.mode != ApplicationMode.AUTO_SUBMIT:
            run = ApplicationRun(
                plan_id=plan.id,
                status=RunStatus.WAITING_FOR_REVIEW,
                execution_log_json=[{"at": datetime.now(timezone.utc).isoformat(), "message": "Review gate enforced before submission"}],
                uploaded_artifacts_json=[str(item) for item in plan.field_map_json.values() if isinstance(item, str) and item],
                result_payload_json={"mode": plan.mode.value, "preview_required": True, "source_policy": plan.source_policy},
            )
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
            self.notifications.enqueue(channel="email", subject=f"Review required: {plan.source_adapter}", body="A staged application is waiting for manual review.")
            return run

        execution = connector.submit_application(plan.field_map_json)
        execution_status = str(execution.get("status") or "failed")
        if execution_status == "submitted":
            run_status = RunStatus.COMPLETED
            plan.terminal_status = ApplicationStatus.SUBMITTED
        elif execution_status == "review_required":
            run_status = RunStatus.WAITING_FOR_REVIEW
            plan.terminal_status = ApplicationStatus.REVIEW_REQUIRED
            plan.approval_state = "required"
        elif execution_status == "blocked":
            run_status = RunStatus.FAILED
            plan.terminal_status = ApplicationStatus.BLOCKED
        else:
            run_status = RunStatus.FAILED
            plan.terminal_status = ApplicationStatus.FAILED

        run = ApplicationRun(
            plan_id=plan.id,
            status=run_status,
            execution_log_json=execution.get("log", []),
            uploaded_artifacts_json=[str(item) for item in plan.field_map_json.values() if isinstance(item, str) and item],
            result_payload_json=execution,
        )
        self.db.add(plan)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        self.notifications.enqueue(channel="email", subject=f"Application {execution_status}", body=f"{plan.source_adapter} application finished with status {execution_status}.")
        return run
