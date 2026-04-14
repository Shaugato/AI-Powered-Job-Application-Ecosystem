from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import PromptVersion
from backend.app.schemas.prompts import PromptVersionCreate, PromptVersionRead

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptVersionRead])
def list_prompts(db: Session = Depends(get_db)) -> list[PromptVersion]:
    return db.query(PromptVersion).order_by(PromptVersion.success_rate_metric.desc(), PromptVersion.created_at.desc()).all()


@router.post("", response_model=PromptVersionRead)
def create_prompt(payload: PromptVersionCreate, db: Session = Depends(get_db)) -> PromptVersion:
    record = PromptVersion(
        name=payload.name,
        role_tags_json=payload.role_tags,
        prompt_text=payload.prompt_text,
        temperature=payload.temperature,
        success_rate_metric=payload.success_rate_metric,
        last_used_at=payload.last_used_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{prompt_id}", response_model=PromptVersionRead)
def update_prompt(prompt_id: str, payload: PromptVersionCreate, db: Session = Depends(get_db)) -> PromptVersion:
    record = db.query(PromptVersion).filter(PromptVersion.id == prompt_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    record.name = payload.name
    record.role_tags_json = payload.role_tags
    record.prompt_text = payload.prompt_text
    record.temperature = payload.temperature
    record.success_rate_metric = payload.success_rate_metric
    record.last_used_at = payload.last_used_at
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{prompt_id}")
def delete_prompt(prompt_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    record = db.query(PromptVersion).filter(PromptVersion.id == prompt_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    db.delete(record)
    db.commit()
    return {"status": "deleted", "id": prompt_id}
