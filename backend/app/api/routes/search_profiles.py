from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import SearchProfile
from backend.app.schemas.search_profile import SearchProfileCreate, SearchProfileRead

router = APIRouter(prefix="/search-profiles", tags=["search-profiles"])


@router.get("", response_model=list[SearchProfileRead])
def list_search_profiles(db: Session = Depends(get_db)) -> list[SearchProfile]:
    return db.query(SearchProfile).order_by(SearchProfile.created_at.desc()).all()


@router.post("", response_model=SearchProfileRead)
def create_search_profile(payload: SearchProfileCreate, db: Session = Depends(get_db)) -> SearchProfile:
    existing = db.query(SearchProfile).filter(SearchProfile.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Search profile already exists")

    record = SearchProfile(
        name=payload.name,
        roles_json=payload.roles,
        keywords_json=payload.keywords,
        excluded_terms_json=payload.excluded_terms,
        locations_json=payload.locations,
        remote_policy=payload.remote_policy,
        salary_floor=payload.salary_floor,
        source_allowlist_json=payload.source_allowlist,
        daily_cap=payload.daily_cap,
        review_policy=payload.review_policy,
        schedule_window_json=payload.schedule_window,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{profile_id}", response_model=SearchProfileRead)
def update_search_profile(profile_id: str, payload: SearchProfileCreate, db: Session = Depends(get_db)) -> SearchProfile:
    record = db.query(SearchProfile).filter(SearchProfile.id == profile_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Search profile not found")

    record.name = payload.name
    record.roles_json = payload.roles
    record.keywords_json = payload.keywords
    record.excluded_terms_json = payload.excluded_terms
    record.locations_json = payload.locations
    record.remote_policy = payload.remote_policy
    record.salary_floor = payload.salary_floor
    record.source_allowlist_json = payload.source_allowlist
    record.daily_cap = payload.daily_cap
    record.review_policy = payload.review_policy
    record.schedule_window_json = payload.schedule_window
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{profile_id}")
def delete_search_profile(profile_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    record = db.query(SearchProfile).filter(SearchProfile.id == profile_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Search profile not found")

    db.delete(record)
    db.commit()
    return {"status": "deleted", "id": profile_id}
