from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.entities import (
    ApplicationOutcome,
    ApplicationPlan,
    GenerationRequest,
    GenerationResult,
    NormalizedJobPosting,
    PromptPerformance,
    PromptVersion,
    ResumeVariantScore,
    ReviewQueueItem,
    SourceAsset,
)
from backend.app.schemas.learning import ApplicationOutcomeCreate


class LearningService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def select_prompt_for_job(self, job: NormalizedJobPosting) -> PromptVersion | None:
        prompts = self.db.query(PromptVersion).all()
        if not prompts:
            return None
        now = datetime.now(timezone.utc)

        def score(prompt: PromptVersion) -> float:
            role_overlap = 0.0
            if prompt.role_tags_json and job.classification_labels_json:
                role_overlap = len(set(prompt.role_tags_json) & set(job.classification_labels_json)) / max(len(set(job.classification_labels_json)), 1)
            recency = 0.0
            if prompt.last_used_at is not None:
                anchor = prompt.last_used_at if prompt.last_used_at.tzinfo else prompt.last_used_at.replace(tzinfo=timezone.utc)
                age_days = max((now - anchor).days, 0)
                recency = max(0.0, 1.0 - min(age_days, 180) / 180)
            return float(prompt.success_rate_metric) + 0.35 * role_overlap + 0.15 * recency

        return max(prompts, key=score)

    def record_outcome(self, payload: ApplicationOutcomeCreate) -> ApplicationOutcome | None:
        plan = self.db.query(ApplicationPlan).filter(ApplicationPlan.id == payload.application_plan_id).first()
        if plan is None:
            return None

        generation_result = self.db.query(GenerationResult).filter(GenerationResult.id == plan.generation_result_id).first()
        request = self.db.query(GenerationRequest).filter(GenerationRequest.id == generation_result.request_id).first() if generation_result else None
        outcome = ApplicationOutcome(
            application_plan_id=plan.id,
            application_run_id=payload.application_run_id,
            generation_result_id=generation_result.id if generation_result else None,
            prompt_version_id=request.prompt_version_id if request else None,
            response_type=payload.response_type,
            interview=payload.interview,
            response_time_days=payload.response_time_days,
            outcome_source=payload.outcome_source,
            notes=payload.notes,
            metadata_json=payload.metadata_json,
            outcome_at=payload.outcome_at or datetime.now(timezone.utc),
        )
        self.db.add(outcome)
        self.db.commit()
        self.db.refresh(outcome)

        if request is not None:
            self._refresh_prompt_performance(request.prompt_version_id)
            self._rebalance_evidence_weights(request.selected_evidence_ids_json, positive=payload.interview)
        if generation_result is not None:
            self.upsert_resume_variant_score(generation_result.id)
        return outcome

    def upsert_resume_variant_score(self, generation_result_id: str) -> ResumeVariantScore | None:
        result = self.db.query(GenerationResult).filter(GenerationResult.id == generation_result_id).first()
        if result is None:
            return None
        request = self.db.query(GenerationRequest).filter(GenerationRequest.id == result.request_id).first()
        if request is None:
            return None
        job = self.db.query(NormalizedJobPosting).filter(NormalizedJobPosting.id == request.job_id).first()
        if job is None:
            return None
        outcomes = self.db.query(ApplicationOutcome).filter(ApplicationOutcome.generation_result_id == generation_result_id).all()
        interviews = sum(1 for outcome in outcomes if outcome.interview)
        interview_rate = interviews / max(len(outcomes), 1) if outcomes else 0.0
        keyword_coverage = float(result.qa_scores_json.get("keyword_coverage", 0.0))
        hallucination_risk = float(result.qa_scores_json.get("hallucination_risk", 0.0))
        score = round(0.5 * keyword_coverage + 0.2 * (1.0 - hallucination_risk) + 0.3 * interview_rate, 4)

        record = self.db.query(ResumeVariantScore).filter(ResumeVariantScore.generation_result_id == generation_result_id).first()
        if record is None:
            record = ResumeVariantScore(generation_result_id=generation_result_id)
        record.role_tag = job.classification_labels_json[0] if job.classification_labels_json else None
        record.score = score
        record.keyword_coverage = keyword_coverage
        record.hallucination_risk = hallucination_risk
        record.interview_rate_proxy = round(interview_rate, 4)
        record.metadata_json = {"outcome_count": len(outcomes), "job_id": job.id}
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def learning_signals(self) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for item in self.db.query(ReviewQueueItem).order_by(ReviewQueueItem.created_at.desc()).limit(25).all():
            signals.append(
                {
                    "source": "review_queue",
                    "signal_type": str(item.reason.value),
                    "related_id": item.id,
                    "status": str(item.status.value),
                    "summary": item.summary,
                    "details_json": dict(item.details_json or {}),
                }
            )
        for result in self.db.query(GenerationResult).order_by(GenerationResult.created_at.desc()).limit(25).all():
            verifier = dict(result.verifier_output_json or {})
            repair = list(result.repair_attempts_json or [])
            if verifier or repair:
                signals.append(
                    {
                        "source": "generation",
                        "signal_type": "verifier",
                        "related_id": result.id,
                        "status": result.compile_status,
                        "summary": f"Verifier tracked {len(verifier.get('issues') or [])} issues and {len(repair)} repair attempts.",
                        "details_json": {
                            "verifier_output": verifier,
                            "repair_attempts": repair,
                        },
                    }
                )
        for asset in self.db.query(SourceAsset).order_by(SourceAsset.created_at.desc()).limit(25).all():
            metadata = dict(asset.metadata_json or {})
            if metadata.get("ambiguity_flags") or float(metadata.get("parser_confidence") or 0.0) < 0.78:
                signals.append(
                    {
                        "source": "ingestion",
                        "signal_type": "parser_quality",
                        "related_id": asset.id,
                        "status": asset.parse_status,
                        "summary": f"Asset {asset.file_name} parsed with confidence {float(metadata.get('parser_confidence') or 0.0):.2f}.",
                        "details_json": metadata,
                    }
                )
        return signals[:50]

    def _refresh_prompt_performance(self, prompt_version_id: str | None) -> None:
        if not prompt_version_id:
            return
        prompt = self.db.query(PromptVersion).filter(PromptVersion.id == prompt_version_id).first()
        if prompt is None:
            return

        requests = self.db.query(GenerationRequest).filter(GenerationRequest.prompt_version_id == prompt_version_id).all()
        request_by_id = {request.id: request for request in requests}
        results = self.db.query(GenerationResult).filter(GenerationResult.request_id.in_(request_by_id.keys())).all() if request_by_id else []
        result_by_id = {result.id: result for result in results}
        plans = self.db.query(ApplicationPlan).filter(ApplicationPlan.generation_result_id.in_(result_by_id.keys())).all() if result_by_id else []
        plan_by_id = {plan.id: plan for plan in plans}
        outcomes = self.db.query(ApplicationOutcome).filter(ApplicationOutcome.application_plan_id.in_(plan_by_id.keys())).all() if plan_by_id else []

        grouped: dict[str, list[ApplicationOutcome]] = defaultdict(list)
        for outcome in outcomes:
            grouped["all"].append(outcome)
            plan = plan_by_id.get(outcome.application_plan_id)
            if plan is None:
                continue
            result = result_by_id.get(plan.generation_result_id)
            if result is None:
                continue
            request = request_by_id.get(result.request_id)
            if request is None:
                continue
            job = self.db.query(NormalizedJobPosting).filter(NormalizedJobPosting.id == request.job_id).first()
            if job is None:
                continue
            for role in job.classification_labels_json or ["all"]:
                grouped[role].append(outcome)

        self.db.query(PromptPerformance).filter(PromptPerformance.prompt_version_id == prompt_version_id).delete()
        global_samples = len(grouped.get("all", []))
        prompt.success_rate_metric = round(sum(1 for item in grouped.get("all", []) if item.interview) / max(global_samples, 1), 4) if global_samples else 0.0
        prompt.last_used_at = datetime.now(timezone.utc)
        self.db.add(prompt)

        for role_tag, role_outcomes in grouped.items():
            sample_size = len(role_outcomes)
            if sample_size == 0:
                continue
            response_times = [item.response_time_days for item in role_outcomes if item.response_time_days is not None]
            last_outcome_at = max((item.outcome_at for item in role_outcomes if item.outcome_at is not None), default=None)
            self.db.add(
                PromptPerformance(
                    prompt_version_id=prompt_version_id,
                    role_tag=role_tag,
                    applications_count=sample_size,
                    interviews_count=sum(1 for item in role_outcomes if item.interview),
                    success_rate=round(sum(1 for item in role_outcomes if item.interview) / sample_size, 4),
                    avg_response_time_days=round(sum(response_times) / len(response_times), 2) if response_times else None,
                    last_outcome_at=last_outcome_at,
                    metadata_json={"prompt_name": prompt.name},
                )
            )
        self.db.commit()

    def _rebalance_evidence_weights(self, evidence_ids: list[str], *, positive: bool) -> None:
        if not evidence_ids:
            return
        from backend.app.models.entities import EvidenceFragment

        delta = 0.05 if positive else -0.02
        fragments = self.db.query(EvidenceFragment).filter(EvidenceFragment.id.in_(evidence_ids)).all()
        for fragment in fragments:
            fragment.success_weight = max(0.5, min(2.5, float(fragment.success_weight) + delta))
            self.db.add(fragment)
        self.db.commit()
