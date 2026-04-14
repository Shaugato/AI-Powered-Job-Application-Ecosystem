from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.entities import CandidateMemoryProfile, MemoryEmbedding, NormalizedJobPosting, OpportunityFit, StructuredSection, StructuredSectionType
from backend.app.services.llm import parse_job_requirement_profile
from backend.app.services.reranking import RerankerService


KEYWORDS = {
    "DevOps": {"terraform", "kubernetes", "ci", "cd", "devops", "sre", "ansible", "jenkins"},
    "Cloud": {"aws", "azure", "gcp", "cloud", "ec2", "lambda"},
    "Networking": {"network", "routing", "switching", "firewall", "vpn", "ccna"},
    "Security": {"security", "siem", "soc", "iam", "incident", "vulnerability"},
    "IT Support": {"support", "service", "desktop", "active directory", "itil"},
    "Infrastructure": {"linux", "windows", "vmware", "backup", "storage", "infrastructure"},
}


@dataclass
class SectionMatch:
    section: StructuredSection
    score: float
    components: dict[str, float]
    rerank_score: float = 0.0

    def evidence_pack_item(self) -> dict[str, Any]:
        return {
            "section_id": self.section.id,
            "section_type": self.section.section_type.value,
            "title": self.section.title,
            "subtitle": self.section.subtitle,
            "text": self.section.body_text,
            "bullets": list(self.section.body_lines_json or []),
            "keywords": list(self.section.keywords_json or []),
            "role_tags": list(self.section.role_tags_json or []),
            "score": float(self.score),
            "rerank_score": float(self.rerank_score),
            "evidence_spans": list(self.section.evidence_spans_json or []),
            "cluster_id": self.section.cluster_id,
        }


@dataclass
class OpportunityFitResult:
    fit: OpportunityFit
    top_sections: list[SectionMatch]
    requirement_profile: dict[str, Any]
    evidence_pack: list[dict[str, Any]]


def classify_job_labels(description: str, title: str = "") -> list[str]:
    haystack = f"{title}\n{description}".lower()
    labels = [label for label, words in KEYWORDS.items() if any(word in haystack for word in words)]
    return labels or ["Infrastructure"]


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.-]{3,}", text.lower()))


def bm25_like_score(job_text: str, section_text: str) -> float:
    left = tokenize(job_text)
    right = tokenize(section_text)
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), 1)


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return numerator / (left_norm * right_norm)


class RetrievalService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.reranker = RerankerService()

    def retrieve(self, job: NormalizedJobPosting, limit: int = 12) -> list[StructuredSection]:
        return [item.section for item in self.rank_sections(job, limit=limit)]

    def rank_sections(self, job: NormalizedJobPosting, *, limit: int = 12) -> list[SectionMatch]:
        requirement_profile = self._job_requirement_profile(job)
        sections = (
            self.db.query(StructuredSection)
            .filter(
                StructuredSection.section_type.in_(
                    [
                        StructuredSectionType.EXPERIENCE,
                        StructuredSectionType.PROJECT,
                        StructuredSectionType.TECHNICAL_SKILL,
                        StructuredSectionType.CERTIFICATION,
                        StructuredSectionType.SUMMARY,
                        StructuredSectionType.EDUCATION,
                    ]
                )
            )
            .all()
        )
        embeddings = {row.structured_section_id: row.embedding for row in self.db.query(MemoryEmbedding).all()}
        matches = [self._rank_section(job, section, embeddings.get(section.id), requirement_profile) for section in sections]
        matches = [match for match in matches if match.score > 0]
        matches.sort(key=lambda item: item.score, reverse=True)
        dense_top = matches[: max(limit * 3, 18)]
        query = self._rerank_query(job, requirement_profile)
        reranked = self.reranker.rerank(
            query,
            [
                {
                    "section_id": item.section.id,
                    "text": self._section_text(item.section),
                    "keywords": list(item.section.keywords_json or []),
                    "dense_score": item.score,
                }
                for item in dense_top
            ],
        )
        rerank_scores = {item["section_id"]: float(item.get("rerank_score") or 0.0) for item in reranked}
        for match in dense_top:
            match.rerank_score = rerank_scores.get(match.section.id, 0.0)
            match.score = round(0.7 * match.score + 0.3 * match.rerank_score, 6)
        dense_top.sort(key=lambda item: item.score, reverse=True)
        return dense_top[:limit]

    def build_opportunity_fit(self, job: NormalizedJobPosting) -> OpportunityFitResult:
        requirement_profile = self._job_requirement_profile(job)
        ranked = self.rank_sections(job, limit=16)
        evidence_pack = [item.evidence_pack_item() for item in ranked[:10]]
        matched_sections = [item.section.id for item in ranked[:10]]
        profile = self.db.query(CandidateMemoryProfile).order_by(CandidateMemoryProfile.updated_at.desc()).first()
        profile_skills = {skill.casefold() for skill in (profile.skills_json if profile else [])}
        required_skills = [str(skill).strip() for skill in requirement_profile.get("required_skills") or [] if str(skill).strip()]
        missing_signals = [skill for skill in required_skills if skill.casefold() not in profile_skills]
        semantic = round(sum(item.components["semantic"] for item in ranked[:8]) / max(min(len(ranked), 8), 1), 4) if ranked else 0.0
        lexical = round(sum(item.components["lexical"] for item in ranked[:8]) / max(min(len(ranked), 8), 1), 4) if ranked else 0.0
        rerank = round(sum(item.rerank_score for item in ranked[:8]) / max(min(len(ranked), 8), 1), 4) if ranked else 0.0
        role_match = 1.0 if requirement_profile.get("role_family") in (profile.role_signals_json if profile else []) else 0.0
        certification_fit = 1.0 if any(cert.casefold() in {value.casefold() for value in (profile.certifications_json if profile else [])} for cert in requirement_profile.get("certifications") or []) else 0.0
        location_fit = 1.0 if not job.location or not profile or not profile.location else float(job.location.lower() in profile.location.lower())
        prior_success = 0.0
        fit_score = round(0.28 * semantic + 0.2 * lexical + 0.22 * rerank + 0.15 * role_match + 0.1 * certification_fit + 0.03 * location_fit + 0.02 * prior_success, 4)
        explanations = []
        if ranked:
            explanations.append(f"Top matched evidence came from {len(ranked[:5])} canonical memory sections after reranking.")
        if requirement_profile.get("role_family"):
            explanations.append(f"Role family aligned to {requirement_profile['role_family']}.")
        if missing_signals:
            explanations.append(f"Missing or weak signals: {', '.join(missing_signals[:5])}.")
        fit = self.db.query(OpportunityFit).filter(OpportunityFit.job_id == job.id).first() or OpportunityFit(job_id=job.id, profile_id=profile.id if profile else None)
        fit.profile_id = profile.id if profile else None
        fit.fit_score = fit_score
        fit.component_scores_json = {
            "semantic": semantic,
            "lexical": lexical,
            "rerank": rerank,
            "role_match": role_match,
            "certification_fit": certification_fit,
            "location_fit": location_fit,
            "prior_success": prior_success,
        }
        fit.matched_section_ids_json = matched_sections
        fit.missing_signals_json = missing_signals[:12]
        fit.explanation_json = explanations
        fit.metadata_json = {"requirement_profile": requirement_profile, "evidence_pack_size": len(evidence_pack)}
        fit.requirement_profile_json = requirement_profile
        fit.rerank_scores_json = [
            {
                "section_id": item.section.id,
                "rerank_score": item.rerank_score,
                "final_score": item.score,
                "dense_components": item.components,
            }
            for item in ranked[:10]
        ]
        self.db.add(fit)
        self.db.flush()
        return OpportunityFitResult(fit=fit, top_sections=ranked, requirement_profile=requirement_profile, evidence_pack=evidence_pack)

    def _rank_section(self, job: NormalizedJobPosting, section: StructuredSection, embedding: list[float] | None, requirement_profile: dict[str, Any]) -> SectionMatch:
        semantic = cosine_similarity(job.embedding, embedding)
        lexical = bm25_like_score(job.description_text, section.body_text)
        role_match = self._section_role_match(requirement_profile, section)
        keyword_hits = self._keyword_hits(requirement_profile, section)
        section_priority = {
            StructuredSectionType.EXPERIENCE: 1.0,
            StructuredSectionType.PROJECT: 0.9,
            StructuredSectionType.TECHNICAL_SKILL: 0.7,
            StructuredSectionType.CERTIFICATION: 0.6,
            StructuredSectionType.SUMMARY: 0.5,
            StructuredSectionType.EDUCATION: 0.35,
        }.get(section.section_type, 0.25)
        score = (0.42 * semantic + 0.28 * lexical + 0.18 * role_match + 0.12 * keyword_hits) * section_priority
        return SectionMatch(
            section=section,
            score=round(score, 6),
            components={
                "semantic": round(semantic, 4),
                "lexical": round(lexical, 4),
                "role_match": round(role_match, 4),
                "keyword_hits": round(keyword_hits, 4),
            },
        )

    def _section_role_match(self, requirement_profile: dict[str, Any], section: StructuredSection) -> float:
        role_family = str(requirement_profile.get("role_family") or "").strip()
        if not role_family:
            return 0.0
        section_roles = {tag.casefold() for tag in section.role_tags_json or []}
        return 1.0 if role_family.casefold() in section_roles else 0.0

    def _keyword_hits(self, requirement_profile: dict[str, Any], section: StructuredSection) -> float:
        needed = {item.casefold() for item in (requirement_profile.get("required_skills") or [])}
        if not needed:
            return 0.0
        section_terms = {item.casefold() for item in (section.keywords_json or [])}
        if not section_terms:
            section_terms = tokenize(section.body_text)
        return len(needed & section_terms) / max(len(needed), 1)

    def _job_requirement_profile(self, job: NormalizedJobPosting) -> dict[str, Any]:
        metadata = job.metadata_json or {}
        cached = metadata.get("requirement_profile")
        if isinstance(cached, dict) and cached:
            return cached
        parsed = parse_job_requirement_profile(job.title, job.description_text, location=job.location, work_mode=job.work_mode, db=self.db)
        metadata["requirement_profile"] = parsed
        if not job.classification_labels_json:
            job.classification_labels_json = classify_job_labels(job.description_text, job.title)
        job.metadata_json = metadata
        self.db.add(job)
        self.db.flush()
        return parsed

    def _rerank_query(self, job: NormalizedJobPosting, requirement_profile: dict[str, Any]) -> str:
        parts = [job.title, job.description_text]
        parts.extend(str(item) for item in (requirement_profile.get("required_skills") or []))
        parts.extend(str(item) for item in (requirement_profile.get("responsibilities") or []))
        return "\n".join(part for part in parts if part)

    def _section_text(self, section: StructuredSection) -> str:
        return "\n".join(part for part in [section.title or "", section.subtitle or "", section.body_text] if part).strip()
