from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import BaseProfile
from backend.app.schemas.base_profile import BaseProfileCreate, BaseProfileRead, BaseProfileUpdate

router = APIRouter(prefix="/base-profiles", tags=["base-profiles"])


@router.get("", response_model=list[BaseProfileRead])
def list_base_profiles(db: Session = Depends(get_db)) -> list[BaseProfile]:
    return db.query(BaseProfile).order_by(BaseProfile.created_at.desc()).all()


@router.post("", response_model=BaseProfileRead)
def create_base_profile(payload: BaseProfileCreate, db: Session = Depends(get_db)) -> BaseProfile:
    record = BaseProfile(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{profile_id}", response_model=BaseProfileRead)
def update_base_profile(profile_id: str, payload: BaseProfileUpdate, db: Session = Depends(get_db)) -> BaseProfile:
    record = db.query(BaseProfile).filter(BaseProfile.id == profile_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Base profile not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{profile_id}")
def delete_base_profile(profile_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    record = db.query(BaseProfile).filter(BaseProfile.id == profile_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Base profile not found")

    db.delete(record)
    db.commit()
    return {"status": "deleted", "id": profile_id}
