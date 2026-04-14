from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.entities import (
    BaseProfile,
    CandidateMemoryProfile,
    EvidenceFragment,
    FragmentType,
    MemoryEmbedding,
    PipelineEntityType,
    PipelineStageName,
    SourceAsset,
    SourceAssetKind,
    StructuredSection,
    StructuredSectionType,
    TruthStatus,
)
from backend.app.services.llm import get_llm_provider
from backend.app.services.pipeline_state import PipelineStateService
from backend.app.services.profile_fusion import ProfileFusionService

SECTION_SORT_ORDER = {
    StructuredSectionType.IDENTITY: 0,
    StructuredSectionType.SUMMARY: 1,
    StructuredSectionType.TECHNICAL_SKILL: 2,
    StructuredSectionType.EXPERIENCE: 3,
    StructuredSectionType.PROJECT: 4,
    StructuredSectionType.CERTIFICATION: 5,
    StructuredSectionType.EDUCATION: 6,
    StructuredSectionType.COVER_LETTER_BODY: 7,
    StructuredSectionType.PROMPT_LOGIC: 8,
}


class StructuredMemoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = get_llm_provider(db)
        self.pipeline_state = PipelineStateService(db)

    def store_asset(
        self,
        *,
        source_document: str,
        file_name: str,
        asset_kind: str,
        normalized_text: str,
        library_key: str | None,
        library_path: str | None,
        payload: dict[str, Any],
        role_tags: list[str],
        truth_status: TruthStatus,
        parser_version: str = "structured-memory-v3",
        source_metadata: dict[str, Any] | None = None,
        page_count: int | None = None,
        stage_records: list[dict[str, Any]] | None = None,
    ) -> SourceAsset:
        content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        asset = SourceAsset(
            source_document=source_document,
            file_name=file_name,
            asset_kind=self._asset_kind(asset_kind),
            content_hash=content_hash,
            parse_status="parsed",
            parser_version=parser_version,
            library_key=library_key,
            library_path=library_path,
            normalized_text=normalized_text,
            page_count=page_count,
            source_metadata_json=source_metadata,
            metadata_json={
                "role_tags": role_tags,
                "role_signals": list(payload.get("role_signals") or []),
                "truth_status": truth_status.value,
                "parser_confidence": float(payload.get("parser_confidence") or 0.0),
                "ambiguity_flags": list(payload.get("ambiguity_flags") or []),
                "layout_blueprint": payload.get("layout_blueprint") or {},
            },
        )
        self.db.add(asset)
        self.db.flush()

        sections = self._sections_from_payload(asset.id, payload, role_tags)
        embeddings = self.provider.embed_texts([self._embedding_text(section) for section in sections]) if sections else []
        for section, embedding in zip(sections, embeddings):
            self.db.add(section)
            self.db.flush()
            self.db.add(
                MemoryEmbedding(
                    structured_section_id=section.id,
                    embedding=embedding,
                    metadata_json={
                        "section_type": section.section_type.value,
                        "cluster_id": section.cluster_id,
                    },
                )
            )

        if stage_records:
            self._record_pipeline(asset.id, stage_records)

        self._mirror_legacy_fragments(source_document, payload, role_tags, truth_status)
        self._refresh_memory_profile()
        return asset

    def latest_profile(self) -> CandidateMemoryProfile | None:
        return self.db.query(CandidateMemoryProfile).order_by(CandidateMemoryProfile.updated_at.desc()).first()

    def memory_snapshot(self) -> dict[str, Any]:
        profile = self.latest_profile()
        sections = self.db.query(StructuredSection).order_by(StructuredSection.sort_order.asc(), StructuredSection.created_at.asc()).all()
        grouped: dict[StructuredSectionType, list[StructuredSection]] = defaultdict(list)
        for section in sections:
            grouped[section.section_type].append(section)
        return {
            "profile_id": profile.id if profile else None,
            "identity": {
                "full_name": profile.full_name if profile else None,
                "email": profile.email if profile else None,
                "phone": profile.phone if profile else None,
                "location": profile.location if profile else None,
                "website": profile.website if profile else None,
            },
            "summary": profile.summary_text if profile else None,
            "role_signals": list(profile.role_signals_json or []) if profile else [],
            "skills": list(profile.skills_json or []) if profile else [],
            "certifications": list(profile.certifications_json or []) if profile else [],
            "experience": [self._section_entry(section) for section in grouped.get(StructuredSectionType.EXPERIENCE, [])],
            "projects": [self._section_entry(section) for section in grouped.get(StructuredSectionType.PROJECT, [])],
            "education": [section.body_text for section in grouped.get(StructuredSectionType.EDUCATION, [])],
            "assets": self.db.query(SourceAsset).count(),
            "section_counts": {section_type.value: len(items) for section_type, items in grouped.items()},
            "profile_metadata": dict(profile.metadata_json or {}) if profile else {},
        }

    def list_asset_sections(self, asset_id: str) -> list[StructuredSection]:
        return (
            self.db.query(StructuredSection)
            .filter(StructuredSection.asset_id == asset_id)
            .order_by(StructuredSection.sort_order.asc(), StructuredSection.created_at.asc())
            .all()
        )

    def sections_for_types(self, section_types: list[StructuredSectionType]) -> list[StructuredSection]:
        if not section_types:
            return []
        return (
            self.db.query(StructuredSection)
            .filter(StructuredSection.section_type.in_(section_types))
            .order_by(StructuredSection.sort_order.asc(), StructuredSection.updated_at.desc())
            .all()
        )

    def embedding_map(self) -> dict[str, list[float] | None]:
        rows = self.db.query(MemoryEmbedding).all()
        return {row.structured_section_id: row.embedding for row in rows}

    def _record_pipeline(self, asset_id: str, stage_records: list[dict[str, Any]]) -> None:
        stage_map = {
            "file_intake": PipelineStageName.FILE_INTAKE,
            "docling_conversion": PipelineStageName.DOCLING_CONVERSION,
            "page_rendering": PipelineStageName.PAGE_RENDERING,
            "layout_zoning": PipelineStageName.LAYOUT_ZONING,
            "structured_extraction": PipelineStageName.STRUCTURED_EXTRACTION,
        }
        for stage in stage_records:
            stage_name = stage_map.get(str(stage.get("stage_name") or ""))
            if stage_name is None:
                continue
            self.pipeline_state.record_stage(
                entity_type=PipelineEntityType.ASSET,
                entity_id=asset_id,
                stage_name=stage_name,
                stage_index=int(stage.get("stage_index") or 0),
                status=str(stage.get("status") or "pending"),
                payload=dict(stage.get("payload") or {}),
                confidence=float(stage.get("confidence") or 0.0),
                provenance=list(stage.get("provenance") or []),
                validation_result=dict(stage.get("validation_result") or {}),
                repair_hints=list(stage.get("repair_hints") or []),
                ambiguity_flags=list(stage.get("ambiguity_flags") or []),
            )

    def _refresh_memory_profile(self) -> CandidateMemoryProfile:
        return ProfileFusionService(self.db).refresh()

    def _sections_from_payload(self, asset_id: str, payload: dict[str, Any], role_tags: list[str]) -> list[StructuredSection]:
        sections: list[StructuredSection] = []
        metadata = payload.get("section_metadata") or {}
        identity = payload.get("identity") or {}
        identity_lines = [value for value in [identity.get("full_name"), identity.get("email"), identity.get("phone"), identity.get("location"), identity.get("website")] if str(value or "").strip()]
        if identity_lines:
            identity_meta = metadata.get("identity") or {}
            sections.append(
                StructuredSection(
                    asset_id=asset_id,
                    section_type=StructuredSectionType.IDENTITY,
                    sort_order=SECTION_SORT_ORDER[StructuredSectionType.IDENTITY],
                    title="Identity",
                    subtitle=None,
                    body_text="\n".join(identity_lines),
                    body_lines_json=identity_lines,
                    keywords_json=[],
                    role_tags_json=role_tags,
                    evidence_spans_json=list(identity_meta.get("evidence_spans") or []),
                    canonical_value_json=dict(identity_meta.get("value") or identity),
                    provenance_json=list(identity_meta.get("provenance") or []),
                    confidence_lineage_json=[{"stage": "structured_extraction", "confidence": float(identity_meta.get("confidence") or 0.0)}],
                    confidence=float(identity_meta.get("confidence") or 1.0),
                    metadata_json={"identity": identity},
                )
            )
        summary = str(payload.get("summary") or "").strip()
        if summary:
            summary_meta = metadata.get("summary") or {}
            sections.append(self._section(asset_id, StructuredSectionType.SUMMARY, "Summary", None, [summary], role_tags, metadata_entry=summary_meta))
        for index, skill in enumerate([str(item).strip() for item in payload.get("technical_skills") or payload.get("skills") or [] if str(item).strip()], start=1):
            skill_meta = (metadata.get("technical_skills") or [{}])[index - 1] if index - 1 < len(metadata.get("technical_skills") or []) else {}
            sections.append(self._section(asset_id, StructuredSectionType.TECHNICAL_SKILL, skill, None, [skill], role_tags, keywords=[skill], metadata_entry=skill_meta))
        for index, cert in enumerate([str(item).strip() for item in payload.get("certifications") or [] if str(item).strip()], start=1):
            cert_meta = (metadata.get("certifications") or [{}])[index - 1] if index - 1 < len(metadata.get("certifications") or []) else {}
            sections.append(self._section(asset_id, StructuredSectionType.CERTIFICATION, cert, None, [cert], role_tags, keywords=[cert], metadata_entry=cert_meta))
        for index, line in enumerate([str(item).strip() for item in payload.get("education") or [] if str(item).strip()], start=1):
            edu_meta = (metadata.get("education") or [{}])[index - 1] if index - 1 < len(metadata.get("education") or []) else {}
            sections.append(self._section(asset_id, StructuredSectionType.EDUCATION, line, None, [line], role_tags, keywords=[], metadata_entry=edu_meta))
        for index, entry in enumerate(payload.get("experience") or [], start=1):
            entry_meta = (metadata.get("experience") or [{}])[index - 1] if index - 1 < len(metadata.get("experience") or []) else {}
            sections.append(self._entry_section(asset_id, StructuredSectionType.EXPERIENCE, entry, role_tags, index, metadata_entry=entry_meta))
        for index, entry in enumerate(payload.get("projects") or [], start=1):
            entry_meta = (metadata.get("projects") or [{}])[index - 1] if index - 1 < len(metadata.get("projects") or []) else {}
            sections.append(self._entry_section(asset_id, StructuredSectionType.PROJECT, entry, role_tags, index, metadata_entry=entry_meta))
        for index, paragraph in enumerate([str(item).strip() for item in payload.get("cover_letter_body") or [] if str(item).strip()], start=1):
            paragraph_meta = (metadata.get("cover_letter_body") or [{}])[index - 1] if index - 1 < len(metadata.get("cover_letter_body") or []) else {}
            sections.append(self._section(asset_id, StructuredSectionType.COVER_LETTER_BODY, f"Paragraph {index}", None, [paragraph], role_tags, metadata_entry=paragraph_meta))
        for index, line in enumerate([str(item).strip() for item in payload.get("prompt_logic") or [] if str(item).strip()], start=1):
            prompt_meta = (metadata.get("prompt_logic") or [{}])[index - 1] if index - 1 < len(metadata.get("prompt_logic") or []) else {}
            sections.append(self._section(asset_id, StructuredSectionType.PROMPT_LOGIC, f"Prompt logic {index}", None, [line], role_tags, metadata_entry=prompt_meta))
        return sections

    def _entry_section(self, asset_id: str, section_type: StructuredSectionType, entry: dict[str, Any], role_tags: list[str], index: int, *, metadata_entry: dict[str, Any] | None = None) -> StructuredSection:
        metadata_entry = metadata_entry or {}
        title = str(entry.get("title") or f"Entry {index}").strip()
        subtitle = str(entry.get("subtitle") or "").strip() or None
        bullets = [str(item).strip() for item in entry.get("bullets") or [] if str(item).strip()]
        keywords = self._dedupe([title, *((subtitle or "").split("|") if subtitle else []), *bullets])[:12]
        return self._section(asset_id, section_type, title, subtitle, bullets, role_tags, keywords=keywords, metadata_entry=metadata_entry)

    def _section(
        self,
        asset_id: str,
        section_type: StructuredSectionType,
        title: str,
        subtitle: str | None,
        body_lines: list[str],
        role_tags: list[str],
        *,
        keywords: list[str] | None = None,
        metadata_entry: dict[str, Any] | None = None,
    ) -> StructuredSection:
        body_lines = [line for line in body_lines if str(line).strip()]
        metadata_entry = metadata_entry or {}
        return StructuredSection(
            asset_id=asset_id,
            section_type=section_type,
            sort_order=SECTION_SORT_ORDER[section_type],
            title=title,
            subtitle=subtitle,
            body_text="\n".join(body_lines),
            body_lines_json=body_lines,
            keywords_json=self._dedupe(keywords or body_lines)[:16],
            role_tags_json=role_tags,
            evidence_spans_json=list(metadata_entry.get("evidence_spans") or []),
            canonical_value_json=metadata_entry.get("value"),
            provenance_json=list(metadata_entry.get("provenance") or []),
            confidence_lineage_json=[{"stage": "structured_extraction", "confidence": float(metadata_entry.get("confidence") or 0.0)}],
            confidence=float(metadata_entry.get("confidence") or 1.0),
            metadata_json={"taxonomy": metadata_entry.get("taxonomy")} if metadata_entry else {},
        )

    def _embedding_text(self, section: StructuredSection) -> str:
        return "\n".join(part for part in [section.title or "", section.subtitle or "", section.body_text] if part).strip()

    def _asset_kind(self, value: str) -> SourceAssetKind:
        try:
            return SourceAssetKind(str(value))
        except ValueError:
            return SourceAssetKind.DOCUMENT

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result

    def _section_entry(self, section: StructuredSection) -> dict[str, Any]:
        return {
            "title": section.title or "Entry",
            "subtitle": section.subtitle,
            "bullets": list(section.body_lines_json or []),
            "source_document": None,
            "confidence": section.confidence,
            "cluster_id": section.cluster_id,
        }

    def _mirror_legacy_fragments(self, source_document: str, payload: dict[str, Any], role_tags: list[str], truth_status: TruthStatus) -> None:
        legacy_rows: list[EvidenceFragment] = []
        summary = str(payload.get("summary") or "").strip()
        if summary:
            legacy_rows.append(
                EvidenceFragment(
                    source_document=source_document,
                    fragment_type=FragmentType.SUMMARY,
                    role_tags_json=role_tags,
                    seniority=None,
                    skills_json=list(payload.get("technical_skills") or payload.get("skills") or []),
                    certifications_json=list(payload.get("certifications") or []),
                    truth_status=truth_status,
                    success_weight=1.0,
                    payload_text=summary,
                    metadata_json={"origin": "structured_memory_mirror"},
                    embedding=None,
                )
            )
        for entry in payload.get("experience") or []:
            bullets = [str(item).strip() for item in entry.get("bullets") or [] if str(item).strip()]
            if not bullets:
                continue
            legacy_rows.append(
                EvidenceFragment(
                    source_document=source_document,
                    fragment_type=FragmentType.BULLET,
                    role_tags_json=role_tags,
                    seniority=None,
                    skills_json=list(payload.get("technical_skills") or payload.get("skills") or []),
                    certifications_json=list(payload.get("certifications") or []),
                    truth_status=truth_status,
                    success_weight=1.0,
                    payload_text="\n".join(bullets),
                    metadata_json={"origin": "structured_memory_mirror", "title": entry.get("title")},
                    embedding=None,
                )
            )
        for entry in payload.get("projects") or []:
            bullets = [str(item).strip() for item in entry.get("bullets") or [] if str(item).strip()]
            if not bullets:
                continue
            legacy_rows.append(
                EvidenceFragment(
                    source_document=source_document,
                    fragment_type=FragmentType.PROJECT,
                    role_tags_json=role_tags,
                    seniority=None,
                    skills_json=list(payload.get("technical_skills") or payload.get("skills") or []),
                    certifications_json=list(payload.get("certifications") or []),
                    truth_status=truth_status,
                    success_weight=1.0,
                    payload_text="\n".join(bullets),
                    metadata_json={"origin": "structured_memory_mirror", "title": entry.get("title")},
                    embedding=None,
                )
            )
        for row in legacy_rows:
            self.db.add(row)
