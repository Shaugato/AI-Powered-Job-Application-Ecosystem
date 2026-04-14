from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.models.entities import ApplicationOutcome, PromptPerformance, ResumeVariantScore
from backend.app.schemas.learning import (
    ApplicationOutcomeCreate,
    ApplicationOutcomeRead,
    LearningSignalRead,
    PromptPerformanceRead,
    ResumeVariantScoreRead,
)
from backend.app.services.learning import LearningService

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/outcomes", response_model=list[ApplicationOutcomeRead])
def list_outcomes(db: Session = Depends(get_db)) -> list[ApplicationOutcome]:
    return db.query(ApplicationOutcome).order_by(ApplicationOutcome.created_at.desc()).all()


@router.post("/outcomes", response_model=ApplicationOutcomeRead)
def create_outcome(payload: ApplicationOutcomeCreate, db: Session = Depends(get_db)) -> ApplicationOutcome:
    outcome = LearningService(db).record_outcome(payload)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Application plan not found")
    return outcome


@router.get("/prompt-performance", response_model=list[PromptPerformanceRead])
def list_prompt_performance(db: Session = Depends(get_db)) -> list[PromptPerformance]:
    return db.query(PromptPerformance).order_by(PromptPerformance.updated_at.desc()).all()


@router.get("/resume-scores", response_model=list[ResumeVariantScoreRead])
def list_resume_scores(db: Session = Depends(get_db)) -> list[ResumeVariantScore]:
    return db.query(ResumeVariantScore).order_by(ResumeVariantScore.updated_at.desc()).all()


@router.get("/signals", response_model=list[LearningSignalRead])
def list_learning_signals(db: Session = Depends(get_db)) -> list[LearningSignalRead]:
    return [LearningSignalRead(**item) for item in LearningService(db).learning_signals()]
