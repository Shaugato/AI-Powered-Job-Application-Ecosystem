from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.entities import BaseProfile, CandidateMemoryProfile, SourceAsset, StructuredSection, StructuredSectionType

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover
    fuzz = None

try:
    import networkx as nx
except Exception:  # pragma: no cover
    nx = None


@dataclass
class _ClusterMember:
    section: StructuredSection
    text_key: str
    date_tokens: set[str]
    skill_tokens: set[str]


class ProfileFusionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def refresh(self) -> CandidateMemoryProfile:
        base_profile = self.db.query(BaseProfile).order_by(BaseProfile.updated_at.desc()).first()
        assets = self.db.query(SourceAsset).order_by(SourceAsset.updated_at.desc()).all()
        sections = self.db.query(StructuredSection).order_by(StructuredSection.updated_at.desc()).all()
        self._cluster_sections(sections)
        identity_candidates = [dict(section.metadata_json.get("identity") or {}) for section in sections if section.section_type == StructuredSectionType.IDENTITY and section.metadata_json]
        canonical_identity = self._canonical_identity(identity_candidates, base_profile)
        summary = next((section.body_text for section in sections if section.section_type == StructuredSectionType.SUMMARY and section.body_text), None)
        role_signals = self._dedupe([*self._flatten([asset.metadata_json.get("role_signals", []) for asset in assets if asset.metadata_json]), *self._flatten([section.role_tags_json or [] for section in sections])])
        skills = self._dedupe([section.body_text for section in sections if section.section_type == StructuredSectionType.TECHNICAL_SKILL])
        certifications = self._dedupe([section.body_text for section in sections if section.section_type == StructuredSectionType.CERTIFICATION])
        cluster_counts = Counter(section.cluster_id for section in sections if section.cluster_id)
        profile = self.db.query(CandidateMemoryProfile).order_by(CandidateMemoryProfile.updated_at.desc()).first() or CandidateMemoryProfile()
        profile.base_profile_id = base_profile.id if base_profile else None
        profile.full_name = canonical_identity.get("full_name") or (base_profile.full_name if base_profile else None)
        profile.email = canonical_identity.get("email") or (base_profile.email if base_profile else None)
        profile.phone = canonical_identity.get("phone") or (base_profile.phone if base_profile else None)
        profile.location = canonical_identity.get("location") or (base_profile.location if base_profile else None)
        profile.website = canonical_identity.get("website") or (base_profile.website if base_profile else None)
        profile.summary_text = summary or (base_profile.summary if base_profile else None)
        profile.role_signals_json = role_signals
        profile.preferred_locations_json = self._dedupe([profile.location] if profile.location else [])
        profile.skills_json = skills
        profile.certifications_json = certifications
        profile.metadata_json = {
            "asset_count": len(assets),
            "section_count": len(sections),
            "canonical_entity": canonical_identity,
            "alternate_claims": self._alternate_claims(identity_candidates),
            "provenance_lineage": {
                "source_resume_links": [asset.source_document for asset in assets if asset.source_document],
                "section_cluster_counts": dict(cluster_counts),
            },
            "confidence_lineage": {
                "mean_section_confidence": round(sum(float(section.confidence or 0.0) for section in sections) / max(len(sections), 1), 4),
                "high_confidence_sections": sum(1 for section in sections if float(section.confidence or 0.0) >= 0.85),
            },
            "merge_lineage": [
                {
                    "section_id": section.id,
                    "cluster_id": section.cluster_id,
                    "section_type": section.section_type.value,
                    "source_asset_id": section.asset_id,
                }
                for section in sections
            ],
            "last_refreshed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.add(profile)
        self.db.flush()
        if base_profile:
            base_profile.full_name = profile.full_name or base_profile.full_name
            base_profile.email = profile.email or base_profile.email
            base_profile.phone = profile.phone or base_profile.phone
            base_profile.location = profile.location or base_profile.location
            base_profile.website = profile.website or base_profile.website
            base_profile.summary = profile.summary_text or base_profile.summary
            base_profile.skills_json = skills
            base_profile.certifications_json = certifications
            base_profile.experience_json = [self._section_entry(section) for section in sections if section.section_type == StructuredSectionType.EXPERIENCE]
            base_profile.projects_json = [self._section_entry(section) for section in sections if section.section_type == StructuredSectionType.PROJECT]
            base_profile.education_json = [{"line": section.body_text} for section in sections if section.section_type == StructuredSectionType.EDUCATION]
            metadata = base_profile.metadata_json or {}
            metadata["memory_source_documents"] = [asset.source_document for asset in assets]
            metadata["last_autofill_at"] = datetime.now(timezone.utc).isoformat()
            metadata["autofill_mode"] = "structured_memory_v3"
            base_profile.metadata_json = metadata
            self.db.add(base_profile)
        self.db.flush()
        return profile

    def _cluster_sections(self, sections: list[StructuredSection]) -> None:
        clusterable = [section for section in sections if section.section_type in {StructuredSectionType.EXPERIENCE, StructuredSectionType.PROJECT, StructuredSectionType.EDUCATION, StructuredSectionType.CERTIFICATION, StructuredSectionType.TECHNICAL_SKILL}]
        members = [self._member(section) for section in clusterable]
        if not members:
            return
        if nx is None:
            for member in members:
                member.section.cluster_id = self._cluster_key(member)
                self.db.add(member.section)
            return
        graph = nx.Graph()
        for member in members:
            graph.add_node(member.section.id)
        for index, left in enumerate(members):
            for right in members[index + 1:]:
                if left.section.section_type != right.section.section_type:
                    continue
                score = self._match_score(left, right)
                if score >= 0.72:
                    graph.add_edge(left.section.id, right.section.id)
        by_id = {member.section.id: member for member in members}
        for component in nx.connected_components(graph):
            cluster_id = self._component_cluster_id(component, by_id)
            for section_id in component:
                by_id[section_id].section.cluster_id = cluster_id
                self.db.add(by_id[section_id].section)

    def _member(self, section: StructuredSection) -> _ClusterMember:
        text_key = self._normalize_key(" ".join(part for part in [section.title or "", section.subtitle or "", section.body_text or ""] if part))
        date_tokens = set(re.findall(r"(?:19|20)\d{2}", " ".join([section.subtitle or "", section.body_text or ""])))
        skill_tokens = {token.lower() for token in (section.keywords_json or []) if token}
        return _ClusterMember(section=section, text_key=text_key, date_tokens=date_tokens, skill_tokens=skill_tokens)

    def _match_score(self, left: _ClusterMember, right: _ClusterMember) -> float:
        if fuzz is not None:
            string_score = float(fuzz.token_set_ratio(left.text_key, right.text_key)) / 100.0
        else:
            string_score = 1.0 if left.text_key == right.text_key else 0.0
        temporal = len(left.date_tokens & right.date_tokens) / max(len(left.date_tokens | right.date_tokens), 1) if (left.date_tokens or right.date_tokens) else 0.5
        skill_overlap = len(left.skill_tokens & right.skill_tokens) / max(len(left.skill_tokens | right.skill_tokens), 1) if (left.skill_tokens or right.skill_tokens) else 0.5
        return 0.55 * string_score + 0.25 * temporal + 0.2 * skill_overlap

    def _component_cluster_id(self, component: set[str], by_id: dict[str, _ClusterMember]) -> str:
        titles = sorted(self._normalize_key(by_id[item].section.title or by_id[item].section.body_text or "") for item in component)
        return titles[0][:64] if titles else next(iter(component))

    def _cluster_key(self, member: _ClusterMember) -> str:
        return member.text_key[:64] or member.section.id

    def _canonical_identity(self, identity_candidates: list[dict[str, Any]], base_profile: BaseProfile | None) -> dict[str, Any]:
        fields = ["full_name", "email", "phone", "location", "website"]
        result: dict[str, Any] = {}
        for field in fields:
            values = [str(candidate.get(field) or "").strip() for candidate in identity_candidates if str(candidate.get(field) or "").strip()]
            if base_profile and getattr(base_profile, field, None):
                values.append(str(getattr(base_profile, field) or "").strip())
            values = [value for value in values if value]
            result[field] = Counter(values).most_common(1)[0][0] if values else None
        return result

    def _alternate_claims(self, identity_candidates: list[dict[str, Any]]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        for candidate in identity_candidates:
            for field, value in candidate.items():
                text = str(value or "").strip()
                if text and text not in result[field]:
                    result[field].append(text)
        return dict(result)

    def _flatten(self, values: list[list[str]]) -> list[str]:
        flattened: list[str] = []
        for chunk in values:
            flattened.extend(str(value).strip() for value in chunk if str(value).strip())
        return flattened

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

    def _normalize_key(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    def _section_entry(self, section: StructuredSection) -> dict[str, Any]:
        return {
            "title": section.title or "Entry",
            "subtitle": section.subtitle,
            "bullets": list(section.body_lines_json or []),
            "source_document": None,
            "confidence": float(section.confidence or 0.0),
            "cluster_id": section.cluster_id,
        }
