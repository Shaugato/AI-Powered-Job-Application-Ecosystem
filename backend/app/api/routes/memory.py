from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.profile_memory import MemoryProfileRead
from backend.app.services.profile_memory import ProfileMemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/profile", response_model=MemoryProfileRead)
def get_memory_profile(db: Session = Depends(get_db)) -> MemoryProfileRead:
    return ProfileMemoryService(db).profile_readiness()
