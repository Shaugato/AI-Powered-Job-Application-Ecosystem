import asyncio
import json
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from backend.app.core.config import get_settings
from backend.app.services.document_runtime import DocumentRuntimeBootstrapService
from backend.app.workflows.activities import document_ingestion_activity, profile_fusion_activity

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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
    if settings.document_bootstrap_on_start:
        report = DocumentRuntimeBootstrapService().bootstrap()
        logger.info("document_runtime_bootstrap=%s", json.dumps(report, default=str))
    client = await connect_temporal(settings.temporal_target, settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue=settings.temporal_document_task_queue,
        activities=[document_ingestion_activity, profile_fusion_activity],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
