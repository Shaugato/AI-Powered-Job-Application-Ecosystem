from fastapi import APIRouter, Depends, HTTPException
from typing import Any
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import IngestionRun, IngestionSourceConfig
from backend.app.schemas.ingestion import IngestionRunRead, IngestionSourceConfigCreate, IngestionSourceConfigRead, IngestionTriggerRequest
from backend.app.services.ingestion import IngestionService
from backend.app.services.orchestration import OrchestrationService

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/configs", response_model=list[IngestionSourceConfigRead])
def list_configs(db: Session = Depends(get_db)) -> list[IngestionSourceConfig]:
    return db.query(IngestionSourceConfig).order_by(IngestionSourceConfig.created_at.desc()).all()


@router.post("/configs", response_model=IngestionSourceConfigRead)
def create_config(payload: IngestionSourceConfigCreate, db: Session = Depends(get_db)) -> IngestionSourceConfig:
    return IngestionService(db).create_config(payload)


@router.put("/configs/{config_id}", response_model=IngestionSourceConfigRead)
def update_config(config_id: str, payload: IngestionSourceConfigCreate, db: Session = Depends(get_db)) -> IngestionSourceConfig:
    record = IngestionService(db).update_config(config_id, payload)
    if record is None:
        raise HTTPException(status_code=404, detail="Ingestion config not found")
    return record


@router.delete("/configs/{config_id}")
def delete_config(config_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    deleted = IngestionService(db).delete_config(config_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Ingestion config not found")
    return {"status": "deleted", "id": config_id}


@router.get("/runs", response_model=list[IngestionRunRead])
def list_runs(db: Session = Depends(get_db)) -> list[IngestionRun]:
    return db.query(IngestionRun).order_by(IngestionRun.created_at.desc()).all()


@router.post("/trigger")
async def trigger_ingestion(payload: IngestionTriggerRequest) -> dict[str, Any]:
    result = await OrchestrationService().start_source_monitor(
        payload.config_id,
        iterations=payload.iterations,
        continuous=payload.continuous,
    )
    return {
        "mode": result.mode,
        "workflow_id": result.workflow_id,
        "status": result.status,
        "details": result.details,
    }
