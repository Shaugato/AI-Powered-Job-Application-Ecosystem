from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from temporalio.client import Client

from backend.app.core.config import get_settings
from backend.app.db.session import SessionLocal
from backend.app.schemas.application import ApplicationPlanCreate
from backend.app.schemas.generation import GenerationRequestCreate
from backend.app.services.application import ApplicationService
from backend.app.services.generation import GenerationService
from backend.app.services.ingestion import IngestionService
from backend.app.workflows.pipelines import JobPipelineWorkflow, SourceMonitorWorkflow


@dataclass
class OrchestrationLaunchResult:
    mode: str
    workflow_id: str
    status: str
    details: dict[str, Any]


class OrchestrationService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.task_queue = self.settings.temporal_main_task_queue

    async def start_source_monitor(self, config_id: str, *, iterations: int = 1, continuous: bool = False) -> OrchestrationLaunchResult:
        workflow_id = f"source-monitor-{config_id}" if continuous else f"source-sweep-{config_id}-{iterations}"
        try:
            client = await Client.connect(self.settings.temporal_target, namespace=self.settings.temporal_namespace)
            await client.start_workflow(
                SourceMonitorWorkflow.run,
                args=[config_id, iterations, continuous],
                id=workflow_id,
                task_queue=self.task_queue,
            )
            return OrchestrationLaunchResult(mode="temporal", workflow_id=workflow_id, status="started", details={"continuous": continuous})
        except Exception as exc:
            with SessionLocal() as db:
                service = IngestionService(db)
                result = service.run_config_once(config_id, workflow_id=workflow_id)
                return OrchestrationLaunchResult(
                    mode="synchronous-fallback",
                    workflow_id=workflow_id,
                    status="completed" if result and result.run.status.value == "completed" else "failed",
                    details={"error": f"{type(exc).__name__}: {exc}", "run_id": result.run.id if result else None},
                )

    async def start_job_pipeline(self, job_id: str) -> OrchestrationLaunchResult:
        workflow_id = f"job-pipeline-{job_id}"
        try:
            client = await Client.connect(self.settings.temporal_target, namespace=self.settings.temporal_namespace)
            await client.start_workflow(JobPipelineWorkflow.run, job_id, id=workflow_id, task_queue=self.task_queue)
            return OrchestrationLaunchResult(mode="temporal", workflow_id=workflow_id, status="started", details={"job_id": job_id})
        except Exception as exc:
            with SessionLocal() as db:
                generation = GenerationService(db).generate(GenerationRequestCreate(job_id=job_id))
                if generation is None:
                    return OrchestrationLaunchResult(mode="synchronous-fallback", workflow_id=workflow_id, status="failed", details={"error": "Generation failed", "exception": f"{type(exc).__name__}: {exc}"})
                plan = ApplicationService(db).create_plan(ApplicationPlanCreate(job_id=job_id, generation_result_id=generation.id))
                run = ApplicationService(db).start_run(plan.id) if plan else None
                return OrchestrationLaunchResult(
                    mode="synchronous-fallback",
                    workflow_id=workflow_id,
                    status="completed" if run is not None else "failed",
                    details={
                        "generation_result_id": generation.id,
                        "plan_id": plan.id if plan else None,
                        "run_id": run.id if run else None,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
