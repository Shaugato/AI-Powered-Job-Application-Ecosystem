from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.models.entities import IngestionRun, IngestionRunStatus, IngestionSourceConfig, SearchProfile, SourceName
from backend.app.schemas.ingestion import IngestionSourceConfigCreate
from backend.app.schemas.jobs import NormalizedJobPostingCreate
from backend.app.services.integrations import IntegrationService
from backend.app.services.jobs import JobService
from backend.app.services.source_registry import SourceRegistry


@dataclass
class IngestionRunResult:
    run: IngestionRun
    pipeline_job_ids: list[str]


class IngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.registry = SourceRegistry.default()
        self.job_service = JobService(db)
        self.integrations = IntegrationService(db)

    def create_config(self, payload: IngestionSourceConfigCreate) -> IngestionSourceConfig:
        record = IngestionSourceConfig(
            name=payload.name,
            search_profile_id=payload.search_profile_id,
            connection_id=payload.connection_id,
            source=payload.source,
            enabled=payload.enabled,
            cadence_minutes=payload.cadence_minutes,
            query_text=payload.query_text,
            location_override=payload.location_override,
            max_results=payload.max_results,
            auto_start_pipeline=payload.auto_start_pipeline,
            search_url=str(payload.search_url) if payload.search_url else None,
            metadata_json=payload.metadata_json,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_config(self, config_id: str, payload: IngestionSourceConfigCreate) -> IngestionSourceConfig | None:
        record = self.db.query(IngestionSourceConfig).filter(IngestionSourceConfig.id == config_id).first()
        if record is None:
            return None
        record.name = payload.name
        record.search_profile_id = payload.search_profile_id
        record.connection_id = payload.connection_id
        record.source = payload.source
        record.enabled = payload.enabled
        record.cadence_minutes = payload.cadence_minutes
        record.query_text = payload.query_text
        record.location_override = payload.location_override
        record.max_results = payload.max_results
        record.auto_start_pipeline = payload.auto_start_pipeline
        record.search_url = str(payload.search_url) if payload.search_url else None
        record.metadata_json = payload.metadata_json
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def delete_config(self, config_id: str) -> bool:
        record = self.db.query(IngestionSourceConfig).filter(IngestionSourceConfig.id == config_id).first()
        if record is None:
            return False
        self.db.delete(record)
        self.db.commit()
        return True

    def due_configs(self) -> list[IngestionSourceConfig]:
        now = datetime.now(timezone.utc)
        configs = self.db.query(IngestionSourceConfig).filter(IngestionSourceConfig.enabled.is_(True)).all()
        due: list[IngestionSourceConfig] = []
        for config in configs:
            if config.last_run_at is None:
                due.append(config)
                continue
            anchor = config.last_run_at if config.last_run_at.tzinfo else config.last_run_at.replace(tzinfo=timezone.utc)
            if anchor + timedelta(minutes=config.cadence_minutes) <= now:
                due.append(config)
        return due

    def run_config_once(self, config_id: str, *, workflow_id: str | None = None) -> IngestionRunResult | None:
        config = self.db.query(IngestionSourceConfig).filter(IngestionSourceConfig.id == config_id).first()
        if config is None:
            return None
        run = IngestionRun(config_id=config.id, workflow_id=workflow_id, status=IngestionRunStatus.IN_PROGRESS, metadata_json={})
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        search_profile = self.db.query(SearchProfile).filter(SearchProfile.id == config.search_profile_id).first() if config.search_profile_id else None
        query = self._query_text(config, search_profile)
        location = config.location_override or self._location(search_profile)
        remote_policy = search_profile.remote_policy if search_profile else None
        connector = self.registry.get(config.source.value)
        connection = self.integrations.connection_for_source(config.source.value, preferred_connection_id=config.connection_id, purpose="monitoring")
        connection_payload = self.integrations.connection_runtime_payload(connection)
        metadata = {
            **(config.metadata_json or {}),
            **({"search_url": config.search_url} if config.search_url else {}),
            **connection_payload,
        }

        try:
            discovered_payloads = connector.discover_jobs(
                query=query,
                location=location,
                remote_policy=remote_policy,
                limit=config.max_results,
                metadata=metadata,
            )
            pipeline_job_ids: list[str] = []
            duplicate_count = 0
            ingested_count = 0
            for item in discovered_payloads:
                payload = NormalizedJobPostingCreate.model_validate(
                    {
                        "source": SourceName(config.source.value),
                        "external_id": item["external_id"],
                        "source_url": item["source_url"],
                        "company": item["company"],
                        "title": item["title"],
                        "location": item.get("location"),
                        "work_mode": item.get("work_mode"),
                        "description_text": item["description_text"],
                        "classification_labels": item.get("classification_labels", []),
                        "eligibility_flags": item.get("eligibility_flags", []),
                        "risk_flags": item.get("risk_flags", []),
                        "metadata_json": {
                            **(item.get("metadata_json") or {}),
                            "ingestion_config_id": config.id,
                            "search_query": query,
                            **({"connection_id": connection.id} if connection is not None else {}),
                        },
                    }
                )
                result = self.job_service.upsert_job_with_status(payload)
                if result.status == "created_duplicate":
                    duplicate_count += 1
                if result.status == "created_new":
                    ingested_count += 1
                    if config.auto_start_pipeline:
                        pipeline_job_ids.append(result.job.id)

            config.last_run_at = datetime.now(timezone.utc)
            run.status = IngestionRunStatus.COMPLETED
            run.discovered_count = len(discovered_payloads)
            run.ingested_count = ingested_count
            run.duplicate_count = duplicate_count
            run.pipeline_triggered_count = len(pipeline_job_ids)
            run.metadata_json = {
                "query": query,
                "location": location,
                "source": config.source.value,
                **({"connection_id": connection.id} if connection is not None else {}),
            }
            self.db.add(config)
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
            return IngestionRunResult(run=run, pipeline_job_ids=pipeline_job_ids)
        except Exception as exc:
            run.status = IngestionRunStatus.FAILED
            run.error_message = f"{type(exc).__name__}: {exc}"
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
            return IngestionRunResult(run=run, pipeline_job_ids=[])

    def _query_text(self, config: IngestionSourceConfig, profile: SearchProfile | None) -> str:
        if config.query_text:
            return config.query_text
        if profile is None:
            return "cloud devops"
        parts = [*profile.roles_json, *profile.keywords_json]
        return " ".join(dict.fromkeys(part for part in parts if part)).strip() or profile.name

    def _location(self, profile: SearchProfile | None) -> str | None:
        if profile is None or not profile.locations_json:
            return None
        return profile.locations_json[0]
