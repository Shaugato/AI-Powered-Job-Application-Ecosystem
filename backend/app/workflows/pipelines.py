from __future__ import annotations

from datetime import timedelta
import os
from typing import Any

from temporalio import workflow

DOCUMENT_TASK_QUEUE = os.getenv("TEMPORAL_DOCUMENT_TASK_QUEUE", "job-ecosystem-document-intel")


@workflow.defn
class DocumentIngestionWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        ingestion = await workflow.execute_activity(
            "document_ingestion_activity",
            payload,
            start_to_close_timeout=timedelta(minutes=20),
            task_queue=DOCUMENT_TASK_QUEUE,
        )
        await workflow.execute_activity(
            "profile_fusion_activity",
            start_to_close_timeout=timedelta(minutes=5),
            task_queue=DOCUMENT_TASK_QUEUE,
        )
        return ingestion


@workflow.defn
class ProfileFusionWorkflow:
    @workflow.run
    async def run(self) -> dict[str, Any]:
        return await workflow.execute_activity(
            "profile_fusion_activity",
            start_to_close_timeout=timedelta(minutes=5),
            task_queue=DOCUMENT_TASK_QUEUE,
        )


@workflow.defn
class JobUnderstandingWorkflow:
    @workflow.run
    async def run(self, job_id: str) -> dict[str, Any]:
        return await workflow.execute_activity(
            "job_understanding_activity",
            job_id,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class EvidencePackWorkflow:
    @workflow.run
    async def run(self, job_id: str) -> dict[str, Any]:
        return await workflow.execute_activity(
            "evidence_pack_activity",
            job_id,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class ResumeTailoringWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            "generate_documents_activity",
            payload,
            start_to_close_timeout=timedelta(minutes=20),
        )


@workflow.defn
class ResumeVerificationWorkflow:
    @workflow.run
    async def run(self, generation_result_id: str) -> dict[str, Any]:
        return await workflow.execute_activity(
            "resume_verification_activity",
            generation_result_id,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class RenderAndRepairWorkflow:
    @workflow.run
    async def run(self, generation_result_id: str) -> dict[str, Any]:
        return await workflow.execute_activity(
            "render_and_repair_activity",
            generation_result_id,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class ApplicationExecutionWorkflow:
    @workflow.run
    async def run(self, plan_id: str) -> dict[str, str]:
        return await workflow.execute_activity(
            "execute_application_activity",
            plan_id,
            start_to_close_timeout=timedelta(minutes=20),
        )


@workflow.defn
class CorpusIngestionWorkflow:
    @workflow.run
    async def run(self, path: str) -> dict[str, str]:
        return await workflow.execute_activity(
            "ingest_corpus_activity",
            path,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class JobPipelineWorkflow:
    @workflow.run
    async def run(self, job_id: str) -> dict[str, str]:
        await workflow.execute_child_workflow(
            JobUnderstandingWorkflow.run,
            job_id,
            id=f"job-understanding-{job_id}",
        )
        await workflow.execute_child_workflow(
            EvidencePackWorkflow.run,
            job_id,
            id=f"evidence-pack-{job_id}",
        )
        generation = await workflow.execute_child_workflow(
            ResumeTailoringWorkflow.run,
            {"job_id": job_id},
            id=f"resume-tailoring-{job_id}",
        )
        if generation.get("status") != "completed":
            return {"status": "failed", "job_id": job_id}
        generation_result_id = str(generation.get("generation_result_id"))
        await workflow.execute_child_workflow(
            ResumeVerificationWorkflow.run,
            generation_result_id,
            id=f"resume-verification-{generation_result_id}",
        )
        await workflow.execute_child_workflow(
            RenderAndRepairWorkflow.run,
            generation_result_id,
            id=f"render-and-repair-{generation_result_id}",
        )
        plan = await workflow.execute_activity(
            "create_application_plan_activity",
            args=[job_id, generation_result_id],
            start_to_close_timeout=timedelta(minutes=5),
        )
        if plan.get("status") != "completed":
            return {"status": "failed", "job_id": job_id, "generation_result_id": generation_result_id}
        execution = await workflow.execute_child_workflow(
            ApplicationExecutionWorkflow.run,
            str(plan["plan_id"]),
            id=f"application-execution-{plan['plan_id']}",
        )
        return {
            "status": execution.get("status", "failed"),
            "job_id": job_id,
            "generation_result_id": generation_result_id,
            "plan_id": str(plan["plan_id"]),
            "run_id": str(execution.get("run_id", "")),
        }


@workflow.defn
class SourceMonitorWorkflow:
    @workflow.run
    async def run(self, config_id: str, iterations: int = 1, continuous: bool = False) -> dict[str, Any]:
        iteration = 0
        last_result: dict[str, Any] = {"status": "idle", "config_id": config_id}
        while continuous or iteration < iterations:
            workflow_id = workflow.info().workflow_id
            discovery = await workflow.execute_activity(
                "discover_jobs_activity",
                args=[config_id, workflow_id],
                start_to_close_timeout=timedelta(minutes=15),
            )
            last_result = discovery
            for job_id in discovery.get("pipeline_job_ids", []):
                await workflow.execute_child_workflow(
                    JobPipelineWorkflow.run,
                    str(job_id),
                    id=f"job-pipeline-{job_id}-{iteration}",
                )
            iteration += 1
            if not continuous and iteration >= iterations:
                break
            await workflow.sleep(timedelta(minutes=int(discovery.get("cadence_minutes", 60))))
        return last_result


@workflow.defn
class GenerationWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id"))
        return await workflow.execute_child_workflow(
            ResumeTailoringWorkflow.run,
            payload,
            id=f"generation-{job_id}",
        )


@workflow.defn
class ApplicationWorkflow:
    @workflow.run
    async def run(self, plan_id: str) -> dict[str, str]:
        return await workflow.execute_child_workflow(
            ApplicationExecutionWorkflow.run,
            plan_id,
            id=f"application-{plan_id}",
        )
