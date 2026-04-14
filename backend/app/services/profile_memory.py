from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.models.entities import BaseProfile, ReviewQueueItem, ReviewQueueStatus, SourceAsset
from backend.app.schemas.profile_memory import CandidateMemoryEntry, CandidateMemoryRead, MemoryProfileRead
from backend.app.services.structured_memory import StructuredMemoryService

PLACEHOLDER_NAMES = {"candidate", "candidate profile", "profile"}


class ProfileMemoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.memory = StructuredMemoryService(db)

    def latest_profile(self, profile_id: str | None = None) -> BaseProfile | None:
        if profile_id:
            return self.db.query(BaseProfile).filter(BaseProfile.id == profile_id).first()
        return self.db.query(BaseProfile).order_by(BaseProfile.created_at.desc()).first()

    def hydrate_profile_from_documents(self, source_documents: list[str], profile_id: str | None = None) -> BaseProfile | None:
        return self.sync_to_profile(profile_id, overwrite_summary=False)

    def hydrate_profile_from_texts(self, document_texts: dict[str, str], profile_id: str | None = None) -> BaseProfile | None:
        return self.sync_to_profile(profile_id, overwrite_summary=False)

    def build_memory(self, profile_id: str | None = None) -> CandidateMemoryRead:
        snapshot = self.memory.memory_snapshot()
        profile = self.latest_profile(profile_id)
        source_documents = [asset.source_document for asset in self.db.query(SourceAsset).order_by(SourceAsset.created_at.desc()).all()]
        return CandidateMemoryRead(
            source_profile_id=profile.id if profile else snapshot.get("profile_id"),
            summary=snapshot.get("summary"),
            skills=list(snapshot.get("skills") or []),
            certifications=list(snapshot.get("certifications") or []),
            experience=[self._entry_from_dict(entry) for entry in snapshot.get("experience") or []],
            projects=[self._entry_from_dict(entry) for entry in snapshot.get("projects") or []],
            education=list(snapshot.get("education") or []),
            approved_documents=int(snapshot.get("assets") or 0),
            pending_documents=0,
            source_documents=source_documents,
        )

    def profile_readiness(self) -> MemoryProfileRead:
        snapshot = self.memory.memory_snapshot()
        section_counts = snapshot.get("section_counts") or {}
        assets = self.db.query(SourceAsset).all()
        review_open = self.db.query(ReviewQueueItem).filter(ReviewQueueItem.status == ReviewQueueStatus.OPEN).count()
        confidences = [float((asset.metadata_json or {}).get("parser_confidence") or 0.0) for asset in assets]
        needs_review_assets = sum(1 for asset in assets if (asset.metadata_json or {}).get("ambiguity_flags") or float((asset.metadata_json or {}).get("parser_confidence") or 0.0) < 0.58)
        provenance_summary = {
            "asset_ids": [asset.id for asset in assets],
            "parser_versions": sorted({str(asset.parser_version or "unknown") for asset in assets}),
            "library_keys": [asset.library_key for asset in assets if asset.library_key],
        }
        return MemoryProfileRead(
            profile_id=snapshot.get("profile_id"),
            identity=snapshot.get("identity") or {},
            summary=snapshot.get("summary"),
            role_signals=list(snapshot.get("role_signals") or []),
            skills=list(snapshot.get("skills") or []),
            certifications=list(snapshot.get("certifications") or []),
            asset_count=int(snapshot.get("assets") or 0),
            section_counts={str(key): int(value) for key, value in section_counts.items()},
            readiness={
                "has_identity": bool((snapshot.get("identity") or {}).get("full_name")),
                "has_summary": bool(snapshot.get("summary")),
                "has_experience": section_counts.get("experience", 0) > 0,
                "has_skills": section_counts.get("technical_skill", 0) > 0,
                "review_queue_clear": review_open == 0,
            },
            review_queue_open=review_open,
            needs_review_assets=needs_review_assets,
            average_parsing_confidence=round(sum(confidences) / max(len(confidences), 1), 4) if confidences else 0.0,
            provenance_summary=provenance_summary,
        )

    def sync_to_profile(self, profile_id: str | None = None, overwrite_summary: bool = False) -> BaseProfile | None:
        memory_profile = self.memory._refresh_memory_profile()
        profile = self.latest_profile(profile_id)
        if profile is None:
            full_name = memory_profile.full_name or "Candidate Profile"
            if full_name.casefold() in PLACEHOLDER_NAMES:
                full_name = "Candidate Profile"
            profile = BaseProfile(full_name=full_name)
        profile.full_name = memory_profile.full_name or profile.full_name
        profile.email = memory_profile.email or profile.email
        profile.phone = memory_profile.phone or profile.phone
        profile.location = memory_profile.location or profile.location
        profile.website = memory_profile.website or profile.website
        if overwrite_summary or not profile.summary:
            profile.summary = memory_profile.summary_text or profile.summary
        snapshot = self.memory.memory_snapshot()
        profile.skills_json = list(snapshot.get("skills") or [])
        profile.certifications_json = list(snapshot.get("certifications") or [])
        profile.experience_json = list(snapshot.get("experience") or [])
        profile.projects_json = list(snapshot.get("projects") or [])
        profile.education_json = [{"line": line} for line in snapshot.get("education") or []]
        metadata = profile.metadata_json or {}
        metadata["memory_profile_id"] = memory_profile.id
        metadata["last_autofill_at"] = memory_profile.updated_at.isoformat() if memory_profile.updated_at else None
        profile.metadata_json = metadata
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def _entry_from_dict(self, item: dict) -> CandidateMemoryEntry:
        return CandidateMemoryEntry(
            title=str(item.get("title") or "Untitled"),
            subtitle=str(item.get("subtitle") or "").strip() or None,
            bullets=[str(bullet).strip() for bullet in item.get("bullets") or [] if str(bullet).strip()],
            source_document=str(item.get("source_document") or "").strip() or None,
            confidence=float(item.get("confidence") or 1.0),
        )
