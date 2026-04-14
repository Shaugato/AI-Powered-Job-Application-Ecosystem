from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.models.entities import NormalizedJobPosting
from backend.app.schemas.jobs import NormalizedJobPostingCreate
from backend.app.services.dedupe import are_near_duplicates, fingerprint_job
from backend.app.services.llm import get_llm_provider
from backend.app.services.retrieval import classify_job_labels


@dataclass
class JobUpsertResult:
    job: NormalizedJobPosting
    status: str
    duplicate_of_id: str | None = None


class JobService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = get_llm_provider(db)

    def upsert_job(self, payload: NormalizedJobPostingCreate) -> NormalizedJobPosting:
        return self.upsert_job_with_status(payload).job

    def upsert_job_with_status(self, payload: NormalizedJobPostingCreate) -> JobUpsertResult:
        existing = (
            self.db.query(NormalizedJobPosting)
            .filter(
                NormalizedJobPosting.source == payload.source,
                NormalizedJobPosting.external_id == payload.external_id,
            )
            .first()
        )
        labels = payload.classification_labels or classify_job_labels(payload.description_text, payload.title)
        dedupe_fingerprint = fingerprint_job(payload.company, payload.title, payload.description_text)
        embedding = self.provider.embed_texts([f"{payload.title}\n{payload.description_text}"])[0]

        if existing:
            return JobUpsertResult(
                job=self._apply_updates(existing, payload, labels, dedupe_fingerprint, embedding),
                status="updated_existing",
            )

        near_duplicate = self._find_near_duplicate(payload.description_text)
        metadata = payload.metadata_json or {}
        duplicate_of_id = None
        if near_duplicate:
            duplicate_of_id = near_duplicate.id
            metadata = {**metadata, "duplicate_of": near_duplicate.id}

        record = NormalizedJobPosting(
            source=payload.source,
            external_id=payload.external_id,
            source_url=str(payload.source_url),
            company=payload.company,
            title=payload.title,
            location=payload.location,
            work_mode=payload.work_mode,
            description_text=payload.description_text,
            posted_at=payload.posted_at,
            classification_labels_json=labels,
            eligibility_flags_json=payload.eligibility_flags,
            risk_flags_json=payload.risk_flags,
            dedupe_fingerprint=dedupe_fingerprint,
            metadata_json=metadata,
            embedding=embedding,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return JobUpsertResult(
            job=record,
            status="created_duplicate" if duplicate_of_id else "created_new",
            duplicate_of_id=duplicate_of_id,
        )

    def update_job(self, job_id: str, payload: NormalizedJobPostingCreate) -> NormalizedJobPosting | None:
        record = self.db.query(NormalizedJobPosting).filter(NormalizedJobPosting.id == job_id).first()
        if record is None:
            return None
        labels = payload.classification_labels or classify_job_labels(payload.description_text, payload.title)
        dedupe_fingerprint = fingerprint_job(payload.company, payload.title, payload.description_text)
        embedding = self.provider.embed_texts([f"{payload.title}\n{payload.description_text}"])[0]
        return self._apply_updates(record, payload, labels, dedupe_fingerprint, embedding)

    def _apply_updates(
        self,
        record: NormalizedJobPosting,
        payload: NormalizedJobPostingCreate,
        labels: list[str],
        dedupe_fingerprint: str,
        embedding: list[float],
    ) -> NormalizedJobPosting:
        record.source = payload.source
        record.external_id = payload.external_id
        record.source_url = str(payload.source_url)
        record.company = payload.company
        record.title = payload.title
        record.location = payload.location
        record.work_mode = payload.work_mode
        record.description_text = payload.description_text
        record.posted_at = payload.posted_at
        record.classification_labels_json = labels
        record.eligibility_flags_json = payload.eligibility_flags
        record.risk_flags_json = payload.risk_flags
        record.dedupe_fingerprint = dedupe_fingerprint
        record.metadata_json = payload.metadata_json
        record.embedding = embedding
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def _find_near_duplicate(self, description: str) -> NormalizedJobPosting | None:
        for existing in self.db.query(NormalizedJobPosting).all():
            if are_near_duplicates(existing.description_text, description):
                return existing
        return None
