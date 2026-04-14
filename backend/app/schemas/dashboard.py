from pydantic import BaseModel

from backend.app.schemas.application import ApplicationPlanRead, ApplicationRunRead
from backend.app.schemas.ingestion import IngestionRunRead
from backend.app.schemas.learning import ApplicationOutcomeRead
from backend.app.schemas.corpus import EvidenceFragmentRead
from backend.app.schemas.generation import GenerationResultRead
from backend.app.schemas.jobs import NormalizedJobPostingRead, SourceHealth


class DashboardOverview(BaseModel):
    totals: dict[str, int]
    jobs: list[NormalizedJobPostingRead]
    drafts: list[GenerationResultRead]
    applications: list[ApplicationPlanRead]
    pending_approvals: list[EvidenceFragmentRead]
    recent_runs: list[ApplicationRunRead]
    recent_ingestion_runs: list[IngestionRunRead]
    recent_outcomes: list[ApplicationOutcomeRead]
    source_health: list[SourceHealth]
