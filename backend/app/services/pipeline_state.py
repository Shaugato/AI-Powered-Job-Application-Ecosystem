from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.entities import PipelineEntityType, PipelineStageName, PipelineStageRecord


class PipelineStateService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_stage(
        self,
        *,
        entity_type: PipelineEntityType,
        entity_id: str,
        stage_name: PipelineStageName,
        stage_index: int,
        status: str,
        payload: dict[str, Any] | None = None,
        confidence: float = 0.0,
        provenance: list[dict[str, Any]] | None = None,
        validation_result: dict[str, Any] | None = None,
        repair_hints: list[dict[str, Any]] | None = None,
        ambiguity_flags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PipelineStageRecord:
        record = (
            self.db.query(PipelineStageRecord)
            .filter(
                PipelineStageRecord.entity_type == entity_type,
                PipelineStageRecord.entity_id == entity_id,
                PipelineStageRecord.stage_name == stage_name,
            )
            .first()
        )
        if record is None:
            record = PipelineStageRecord(entity_type=entity_type, entity_id=entity_id, stage_name=stage_name)
        record.stage_index = stage_index
        record.status = status
        record.payload_json = payload or {}
        record.confidence = float(confidence or 0.0)
        record.provenance_json = provenance or []
        record.validation_result_json = validation_result or {}
        record.repair_hints_json = repair_hints or []
        record.ambiguity_flags_json = ambiguity_flags or []
        record.metadata_json = metadata
        self.db.add(record)
        self.db.flush()
        return record

    def list_entity_stages(self, *, entity_type: PipelineEntityType, entity_id: str) -> list[PipelineStageRecord]:
        return (
            self.db.query(PipelineStageRecord)
            .filter(PipelineStageRecord.entity_type == entity_type, PipelineStageRecord.entity_id == entity_id)
            .order_by(PipelineStageRecord.stage_index.asc(), PipelineStageRecord.created_at.asc())
            .all()
        )

    def stage_summary(self, *, entity_type: PipelineEntityType, entity_id: str) -> dict[str, Any]:
        stages = self.list_entity_stages(entity_type=entity_type, entity_id=entity_id)
        return {
            stage.stage_name.value: {
                "status": stage.status,
                "confidence": float(stage.confidence or 0.0),
                "ambiguity_flags": list(stage.ambiguity_flags_json or []),
                "validation_result": dict(stage.validation_result_json or {}),
                "repair_hints": list(stage.repair_hints_json or []),
            }
            for stage in stages
        }
