from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.entities import (
    ApplicationOutcome,
    ApplicationPlan,
    ApplicationRun,
    EvidenceFragment,
    GenerationResult,
    IngestionRun,
    NormalizedJobPosting,
    TruthStatus,
)
from backend.app.schemas.application import ApplicationPlanRead, ApplicationRunRead
from backend.app.schemas.corpus import EvidenceFragmentRead
from backend.app.schemas.dashboard import DashboardOverview
from backend.app.schemas.generation import GenerationResultRead
from backend.app.schemas.ingestion import IngestionRunRead
from backend.app.schemas.jobs import NormalizedJobPostingRead
from backend.app.schemas.learning import ApplicationOutcomeRead
from backend.app.services.source_registry import SourceRegistry


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def overview(self) -> DashboardOverview:
        totals = {
            "jobs": self.db.query(func.count(NormalizedJobPosting.id)).scalar() or 0,
            "drafts": self.db.query(func.count(GenerationResult.id)).scalar() or 0,
            "applications": self.db.query(func.count(ApplicationPlan.id)).scalar() or 0,
            "ingestion_runs": self.db.query(func.count(IngestionRun.id)).scalar() or 0,
            "outcomes": self.db.query(func.count(ApplicationOutcome.id)).scalar() or 0,
            "pending_approvals": self.db.query(func.count(EvidenceFragment.id))
            .filter(EvidenceFragment.truth_status == TruthStatus.PENDING)
            .scalar()
            or 0,
        }
        jobs = self.db.query(NormalizedJobPosting).order_by(NormalizedJobPosting.created_at.desc()).limit(8).all()
        drafts = self.db.query(GenerationResult).order_by(GenerationResult.created_at.desc()).limit(8).all()
        applications = self.db.query(ApplicationPlan).order_by(ApplicationPlan.created_at.desc()).limit(8).all()
        approvals = (
            self.db.query(EvidenceFragment)
            .filter(EvidenceFragment.truth_status == TruthStatus.PENDING)
            .order_by(EvidenceFragment.created_at.desc())
            .limit(8)
            .all()
        )
        runs = self.db.query(ApplicationRun).order_by(ApplicationRun.created_at.desc()).limit(8).all()
        ingestion_runs = self.db.query(IngestionRun).order_by(IngestionRun.created_at.desc()).limit(8).all()
        outcomes = self.db.query(ApplicationOutcome).order_by(ApplicationOutcome.created_at.desc()).limit(8).all()
        registry = SourceRegistry.default()
        return DashboardOverview(
            totals=totals,
            jobs=[NormalizedJobPostingRead.model_validate(item) for item in jobs],
            drafts=[GenerationResultRead.model_validate(item) for item in drafts],
            applications=[ApplicationPlanRead.model_validate(item) for item in applications],
            pending_approvals=[EvidenceFragmentRead.model_validate(item) for item in approvals],
            recent_runs=[ApplicationRunRead.model_validate(item) for item in runs],
            recent_ingestion_runs=[IngestionRunRead.model_validate(item) for item in ingestion_runs],
            recent_outcomes=[ApplicationOutcomeRead.model_validate(item) for item in outcomes],
            source_health=[connector.health() for connector in registry.connectors.values()],
        )
