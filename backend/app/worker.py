import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from backend.app.core.config import get_settings
from backend.app.workflows.activities import (
    create_application_plan_activity,
    discover_jobs_activity,
    evidence_pack_activity,
    execute_application_activity,
    generate_documents_activity,
    ingest_corpus_activity,
    job_understanding_activity,
    render_and_repair_activity,
    resume_verification_activity,
)
from backend.app.workflows.pipelines import (
    ApplicationExecutionWorkflow,
    ApplicationWorkflow,
    CorpusIngestionWorkflow,
    DocumentIngestionWorkflow,
    EvidencePackWorkflow,
    GenerationWorkflow,
    JobPipelineWorkflow,
    JobUnderstandingWorkflow,
    ProfileFusionWorkflow,
    RenderAndRepairWorkflow,
    ResumeTailoringWorkflow,
    ResumeVerificationWorkflow,
    SourceMonitorWorkflow,
)


async def connect_temporal(target: str, namespace: str) -> Client:
    last_error: Exception | None = None
    for attempt in range(1, 21):
        try:
            return await Client.connect(target, namespace=namespace)
        except Exception as exc:  # pragma: no cover
            last_error = exc
            await asyncio.sleep(min(2 * attempt, 10))
    assert last_error is not None
    raise last_error


async def main() -> None:
    settings = get_settings()
    client = await connect_temporal(settings.temporal_target, settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue=settings.temporal_main_task_queue,
        workflows=[
            DocumentIngestionWorkflow,
            ProfileFusionWorkflow,
            JobUnderstandingWorkflow,
            EvidencePackWorkflow,
            ResumeTailoringWorkflow,
            ResumeVerificationWorkflow,
            RenderAndRepairWorkflow,
            ApplicationExecutionWorkflow,
            CorpusIngestionWorkflow,
            GenerationWorkflow,
            ApplicationWorkflow,
            JobPipelineWorkflow,
            SourceMonitorWorkflow,
        ],
        activities=[
            ingest_corpus_activity,
            discover_jobs_activity,
            job_understanding_activity,
            evidence_pack_activity,
            generate_documents_activity,
            resume_verification_activity,
            render_and_repair_activity,
            create_application_plan_activity,
            execute_application_activity,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
