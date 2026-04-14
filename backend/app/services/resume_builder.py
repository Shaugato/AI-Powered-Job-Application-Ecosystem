from __future__ import annotations

import json
import math
from html import escape
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings
from backend.app.models.entities import StructuredSectionType
from backend.app.services.layout_planner import A4LayoutPlanner
from backend.app.services.llm import NullLLMProvider, get_llm_provider
from backend.app.services.renderer import ResumeRenderService
from backend.app.services.verification import ResumeVerifierService

RESUME_REWRITE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": ["string", "null"]},
        "skills": {"type": "array", "items": {"type": "string"}},
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "subtitle": {"type": ["string", "null"]},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "subtitle", "bullets"],
            },
        },
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "subtitle": {"type": ["string", "null"]},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "subtitle", "bullets"],
            },
        },
        "certifications": {"type": "array", "items": {"type": "string"}},
        "education": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "skills", "experience", "projects", "certifications", "education"],
}
COVER_LETTER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "opening": {"type": "string"},
        "body_paragraphs": {"type": "array", "items": {"type": "string"}},
        "closing": {"type": "string"},
    },
    "required": ["opening", "body_paragraphs", "closing"],
}


class ResumeBuilder:
    def __init__(self, db) -> None:
        self.db = db
        self.settings = get_settings()
        self.provider = get_llm_provider(db)
        self.renderer = ResumeRenderService()
        self.verifier = ResumeVerifierService()
        self.planner = A4LayoutPlanner()

    def compose(self, *, job, fit_result, memory_snapshot: dict[str, Any]) -> dict[str, Any]:
        ranked_sections = fit_result.top_sections
        evidence_pack = list(getattr(fit_result, "evidence_pack", []) or [])
        by_type: dict[str, list[Any]] = {}
        for match in ranked_sections:
            by_type.setdefault(match.section.section_type.value, []).append(match.section)
        by_type = {key: self._dedupe_sections(value) for key, value in by_type.items()}

        identity = dict(memory_snapshot.get("identity") or {})
        selected_experience = [entry for entry in (self._section_to_entry(section, default_label="Experience") for section in by_type.get(StructuredSectionType.EXPERIENCE.value, [])[:4]) if entry]
        selected_projects = [entry for entry in (self._section_to_entry(section, default_label="Project") for section in by_type.get(StructuredSectionType.PROJECT.value, [])[:2]) if entry]
        selected_skills = self._dedupe([skill for skill in (self._clean_skill(section.body_text) for section in by_type.get(StructuredSectionType.TECHNICAL_SKILL.value, [])) if skill])[:12]
        if not selected_skills:
            selected_skills = self._dedupe([skill for skill in (self._clean_skill(item) for item in list(memory_snapshot.get("skills") or [])) if skill])[:12]
        selected_certs = self._dedupe([line for line in (self._clean_display_text(section.body_text) for section in by_type.get(StructuredSectionType.CERTIFICATION.value, [])) if line])[:4]
        if not selected_certs:
            selected_certs = self._dedupe([line for line in (self._clean_display_text(item) for item in list(memory_snapshot.get("certifications") or [])) if line])[:4]
        selected_education = [line for line in (self._clean_display_text(section.body_text) for section in by_type.get(StructuredSectionType.EDUCATION.value, [])) if line][:2]
        if not selected_education:
            selected_education = [line for line in (self._clean_display_text(item) for item in list(memory_snapshot.get("education") or [])) if line][:2]

        summary = str(memory_snapshot.get("summary") or "").strip() or None
        draft = {
            "identity": identity,
            "summary": summary,
            "skills": selected_skills,
            "experience": selected_experience,
            "projects": selected_projects,
            "certifications": selected_certs,
            "education": selected_education,
        }
        rewritten = self._rewrite_selected_content(job=job, fit_result=fit_result, draft=draft)
        resume = {
            "identity": identity,
            "summary": self._clean_display_text(rewritten.get("summary")) or summary,
            "skills": self._dedupe([skill for skill in (self._clean_skill(item) for item in (rewritten.get("skills") or selected_skills)) if skill]),
            "experience": [entry for entry in (self._entry_from_dict(item, default_label="Experience") for item in (rewritten.get("experience") or selected_experience)) if entry],
            "projects": [entry for entry in (self._entry_from_dict(item, default_label="Project") for item in (rewritten.get("projects") or selected_projects)) if entry],
            "certifications": self._dedupe([line for line in (self._clean_display_text(item) for item in (rewritten.get("certifications") or selected_certs)) if line]),
            "education": [line for line in (self._clean_display_text(item) for item in (rewritten.get("education") or selected_education)) if line],
        }
        resume, layout_blueprint, trim_decisions = self.planner.plan(
            resume,
            requirement_profile=fit_result.requirement_profile,
        )
        section_budget = dict(layout_blueprint.get("section_budget") or {})
        selected_ids = [
            *(section.id for section in by_type.get(StructuredSectionType.EXPERIENCE.value, [])[: len(resume.get("experience") or [])]),
            *(section.id for section in by_type.get(StructuredSectionType.PROJECT.value, [])[: len(resume.get("projects") or [])]),
            *(section.id for section in by_type.get(StructuredSectionType.TECHNICAL_SKILL.value, [])[: len(resume.get("skills") or [])]),
            *(section.id for section in by_type.get(StructuredSectionType.CERTIFICATION.value, [])[: len(resume.get("certifications") or [])]),
            *(section.id for section in by_type.get(StructuredSectionType.EDUCATION.value, [])[: len(resume.get("education") or [])]),
        ]
        all_ids = [match.section.id for match in ranked_sections]
        excluded_ids = [section_id for section_id in all_ids if section_id not in selected_ids]
        verification = self.verify_resume(
            resume=resume,
            evidence_pack=evidence_pack,
            requirement_profile=fit_result.requirement_profile,
            rendered_metrics={"estimated_pages": 1},
        )
        repair_attempts: list[dict[str, Any]] = []
        if not verification.get("passed"):
            for attempt in range(self.settings.document_max_repair_attempts):
                repaired_resume, repair_record, layout_blueprint, planner_decisions = self.repair_resume(
                    resume=resume,
                    verification=verification,
                    rendered_metrics={"estimated_pages": 1},
                    requirement_profile=fit_result.requirement_profile,
                )
                if not repair_record.get("changed"):
                    break
                resume = repaired_resume
                trim_decisions.extend(planner_decisions)
                repair_attempts.append({"attempt": attempt + 1, **repair_record, "issues": verification.get("issues")})
                verification = self.verify_resume(
                    resume=resume,
                    evidence_pack=evidence_pack,
                    requirement_profile=fit_result.requirement_profile,
                    rendered_metrics={"estimated_pages": 1},
                )
                if verification.get("passed"):
                    break
        cover_letter = self._compose_cover_letter(job=job, fit_result=fit_result, resume=resume)
        rewrite_provenance = {
            "summary": {"selected_evidence_ids": selected_ids[:2], "confidence": 0.72},
            "experience": [{"title": entry.get("title"), "selected_evidence_ids": selected_ids[: len(entry.get("bullets") or [])], "confidence": 0.7} for entry in (resume.get("experience") or [])],
            "projects": [{"title": entry.get("title"), "selected_evidence_ids": selected_ids[: len(entry.get("bullets") or [])], "confidence": 0.7} for entry in (resume.get("projects") or [])],
        }
        self.update_page_plan(resume, layout_blueprint=layout_blueprint, decisions=trim_decisions)
        return {
            "resume": resume,
            "cover_letter": cover_letter,
            "selected_section_ids": selected_ids,
            "excluded_section_ids": excluded_ids,
            "section_budget": section_budget,
            "trim_decisions": trim_decisions,
            "evidence_pack": evidence_pack,
            "layout_blueprint": layout_blueprint,
            "verification": verification,
            "repair_attempts": repair_attempts,
            "rewrite_provenance": rewrite_provenance,
        }

    def render_preview(self, *, artifact_dir: Path, resume: dict[str, Any], job_title: str, company: str) -> tuple[Path, Path | None, dict[str, Any]]:
        html = self.render_resume_preview_html(resume, job_title=job_title, company=company)
        return self.renderer.render(artifact_dir=artifact_dir, html=html, file_stem="resume_preview")

    def verify_resume(
        self,
        *,
        resume: dict[str, Any],
        evidence_pack: list[dict[str, Any]],
        requirement_profile: dict[str, Any],
        rendered_metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.verifier.verify(
            resume=resume,
            evidence_pack=evidence_pack,
            requirement_profile=requirement_profile,
            rendered_metrics=rendered_metrics,
        )

    def repair_resume(
        self,
        *,
        resume: dict[str, Any],
        verification: dict[str, Any],
        rendered_metrics: dict[str, Any] | None,
        requirement_profile: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[str]]:
        working = json.loads(json.dumps(resume))
        verification_repairs = self._repair_resume(working, verification)
        delta = self._delta_from_feedback(verification=verification, rendered_metrics=rendered_metrics or {}, resume=working)
        planner_repairs: list[str] = []
        if delta:
            working, planner_repairs = self.planner.repair(working, delta=delta)
        replanned, layout_blueprint, planning_decisions = self.planner.plan(working, requirement_profile=requirement_profile)
        self.update_page_plan(replanned, layout_blueprint=layout_blueprint, decisions=planning_decisions)
        return replanned, {
            "verification_repairs": verification_repairs,
            "delta": delta,
            "planner_repairs": planner_repairs,
            "changed": bool(verification_repairs or delta or planner_repairs or planning_decisions),
        }, layout_blueprint, planning_decisions

    def update_page_plan(self, resume: dict[str, Any], *, layout_blueprint: dict[str, Any], decisions: list[str], rendered_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        rendered_metrics = dict(rendered_metrics or {})
        estimated_lines = self._estimate_lines(resume)
        page_plan = dict(resume.get("page_plan") or {})
        page_plan.update({
            "paper_size": "A4",
            "target_pages": 1,
            "line_budget": int(layout_blueprint.get("line_budget") or 52),
            "estimated_lines": estimated_lines,
            "fits_on_one_page": estimated_lines <= int(layout_blueprint.get("line_budget") or 52) and int(rendered_metrics.get("estimated_pages") or 1) <= 1 and int(rendered_metrics.get("overflow_px") or 0) <= 0,
            "strategy": "The composer retrieves a ranked evidence pack, rewrites only selected evidence, then applies deterministic one-page A4 budgeting.",
            **self._page_line_breakdown(resume),
            "decisions": self._dedupe(list(decisions or [])),
            "layout_blueprint": layout_blueprint,
            "rendered_metrics": rendered_metrics,
        })
        resume["page_plan"] = page_plan
        return resume

    def _rewrite_selected_content(self, *, job, fit_result, draft: dict[str, Any]) -> dict[str, Any]:
        if isinstance(self.provider, NullLLMProvider):
            return {
                "summary": draft.get("summary"),
                "skills": draft.get("skills") or [],
                "experience": draft.get("experience") or [],
                "projects": draft.get("projects") or [],
                "certifications": draft.get("certifications") or [],
                "education": draft.get("education") or [],
            }
        try:
            return self.provider.generate_json(
                model=self.settings.openai_primary_model,
                instructions=(
                    "Rewrite the selected candidate memory into a natural, ATS-friendly one-page resume draft. "
                    "Do not invent information. Keep the candidate factual and grounded. "
                    "Summary: max 3 sentences. Experience: max 3 bullets per role, each concise. Projects: max 2 bullets each. "
                    "Maintain authenticity while incorporating important job keywords naturally."
                ),
                payload={
                    "job": {
                        "title": job.title,
                        "company": job.company,
                        "description": job.description_text,
                        "fit": fit_result.requirement_profile,
                    },
                    "selected_content": draft,
                },
                schema=RESUME_REWRITE_SCHEMA,
            )
        except Exception:
            return {
                "summary": draft.get("summary"),
                "skills": draft.get("skills") or [],
                "experience": draft.get("experience") or [],
                "projects": draft.get("projects") or [],
                "certifications": draft.get("certifications") or [],
                "education": draft.get("education") or [],
            }

    def _repair_resume(self, resume: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
        hints = list(verification.get("repair_hints") or [])
        if not hints:
            return {}
        applied: dict[str, Any] = {}
        for hint in hints:
            action = hint.get("action")
            if action == "prioritize_required_skills" and resume.get("summary"):
                resume["summary"] = " ".join(str(resume["summary"]).split()[:28])
                applied[action] = True
            elif action == "dedupe_bullets":
                for section_name in ("experience", "projects"):
                    for entry in (resume.get(section_name) or []):
                        entry["bullets"] = self._dedupe(list(entry.get("bullets") or []))
                    resume[section_name] = self._dedupe_entry_list(list(resume.get(section_name) or []))
                applied[action] = True
            elif action == "remove_or_rewrite_claims":
                for section_name in ("experience", "projects"):
                    for entry in (resume.get(section_name) or []):
                        cleaned = []
                        for bullet in (entry.get("bullets") or []):
                            text = str(bullet)
                            if any(text == claim for claim in hint.get("claims") or []):
                                text = text.replace("%", "").replace("+", "")
                            cleaned.append(text)
                        entry["bullets"] = cleaned
                applied[action] = True
            elif action == "reorder_experience":
                resume["experience"] = self.planner._sort_experience_entries(list(resume.get("experience") or []))
                applied[action] = True
            elif action in {"shrink_sections", "rebalance_sections"}:
                applied[action] = True
        return applied

    def _delta_from_feedback(self, *, verification: dict[str, Any], rendered_metrics: dict[str, Any], resume: dict[str, Any]) -> dict[str, Any]:
        delta: dict[str, Any] = {}
        for hint in verification.get("repair_hints") or []:
            suggested = hint.get("delta")
            if isinstance(suggested, dict):
                for key, value in suggested.items():
                    if key not in delta:
                        delta[key] = value
        overflow_px = int(rendered_metrics.get("overflow_px") or 0)
        estimated_pages = int(rendered_metrics.get("estimated_pages") or 1)
        if overflow_px > 0 or estimated_pages > 1:
            delta.setdefault("reduce_summary_lines", 1 if resume.get("summary") else 0)
            delta.setdefault("tighten_spacing_steps", 2 if overflow_px > 48 or estimated_pages > 1 else 1)
            if resume.get("experience"):
                title = (resume.get("experience") or [])[-1].get("title")
                if title:
                    delta.setdefault("compress_experience_titles", [title])
                if overflow_px > 56 and len(resume.get("experience") or []) > 2:
                    delta.setdefault("remove_last_experience", True)
            if resume.get("projects"):
                title = (resume.get("projects") or [])[-1].get("title")
                if title:
                    delta.setdefault("compress_project_titles", [title])
                delta.setdefault("remove_last_project", len(resume.get("projects") or []) > 0)
            delta.setdefault("compact_certifications", bool(resume.get("certifications")))
            delta.setdefault("compact_education", len(resume.get("education") or []) > 1)
            if len(resume.get("skills") or []) > 6:
                delta.setdefault("trim_skills_to", 6 if overflow_px > 48 else 8)
            delta.setdefault("max_experience_bullets", 2 if overflow_px <= 48 else 1)
            delta.setdefault("max_project_bullets", 1 if overflow_px > 24 else 2)
            if overflow_px > 72 and not resume.get("projects") and len(resume.get("experience") or []) <= 2:
                delta.setdefault("drop_summary", True)
        return {key: value for key, value in delta.items() if value not in (None, False, [], {})}

    def _compose_cover_letter(self, *, job, fit_result, resume: dict[str, Any]) -> dict[str, Any]:
        summary = str(resume.get("summary") or "").strip()
        opening = f"I am applying for the {job.title} role at {job.company}."
        paragraph = summary or "My background aligns with the core requirements of the role and the attached resume highlights the most relevant evidence."
        closing = "Thank you for your consideration."
        if isinstance(self.provider, NullLLMProvider):
            return {"opening": opening, "body_paragraphs": [paragraph], "closing": closing}
        try:
            return self.provider.generate_json(
                model=self.settings.openai_review_model,
                instructions=(
                    "Draft a concise, truthful cover letter using only the supplied resume content and job requirements. "
                    "Keep it under three short paragraphs."
                ),
                payload={
                    "job": {"title": job.title, "company": job.company, "requirements": fit_result.requirement_profile},
                    "resume": resume,
                },
                schema=COVER_LETTER_SCHEMA,
            )
        except Exception:
            return {"opening": opening, "body_paragraphs": [paragraph], "closing": closing}

    def _estimate_lines(self, resume: dict[str, Any]) -> int:
        lines = 4
        identity = resume.get("identity") or {}
        identity_count = len([value for value in identity.values() if str(value or "").strip()])
        lines += 1 if identity_count else 0
        if resume.get("summary"):
            lines += max(2, math.ceil(len(str(resume.get("summary") or "").split()) / 11))
        if resume.get("skills"):
            lines += 1 + math.ceil(len(resume["skills"]) / 6)
        for section_name in ("experience", "projects"):
            entries = resume.get(section_name) or []
            if entries:
                lines += 1
            for entry in entries:
                lines += 1 + len(entry.get("bullets") or [])
        if resume.get("certifications"):
            lines += 1 + math.ceil(len(resume["certifications"]) / 3)
        if resume.get("education"):
            lines += 1 + len(resume["education"])
        return lines

    def _dedupe_sections(self, sections: list[Any]) -> list[Any]:
        seen_clusters: set[str] = set()
        seen_signatures: set[str] = set()
        unique: list[Any] = []
        for section in sections:
            cluster = str(getattr(section, 'cluster_id', '') or '').strip().casefold()
            signature = self._normalize_signature(' | '.join([str(getattr(section, 'title', '') or ''), str(getattr(section, 'subtitle', '') or ''), str(getattr(section, 'body_text', '') or '')]))
            if cluster and cluster in seen_clusters:
                continue
            if signature in seen_signatures:
                continue
            if cluster:
                seen_clusters.add(cluster)
            seen_signatures.add(signature)
            unique.append(section)
        return unique

    def _dedupe_entry_list(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for entry in entries:
            bullets = [self._clean_display_text(item) for item in (entry.get('bullets') or []) if self._clean_display_text(item)]
            signature = self._normalize_signature(' | '.join([str(entry.get('title') or ''), str(entry.get('subtitle') or ''), ' || '.join(bullets)]))
            if signature in seen:
                continue
            seen.add(signature)
            result.append(entry)
        return result

    def _normalize_signature(self, value: str) -> str:
        return ' '.join(str(value or '').casefold().split())

    def _section_to_entry(self, section, *, default_label: str) -> dict[str, Any] | None:
        return self._entry_from_dict(
            {
                "title": section.title,
                "subtitle": section.subtitle,
                "bullets": list(section.body_lines_json or []),
            },
            default_label=default_label,
        )

    def _entry_from_dict(self, entry: dict[str, Any], *, default_label: str) -> dict[str, Any] | None:
        title = self._clean_display_text(entry.get("title"))
        subtitle = self._clean_display_text(entry.get("subtitle")) or None
        if title and (self._looks_like_noise(title) or any(token in title.lower() for token in ["resume", "curriculum vitae", "cover letter", "prompt"])):
            title = ""
        if subtitle and self._looks_like_noise(subtitle):
            subtitle = None
        if not title and subtitle:
            title, subtitle = subtitle, None
        bullets = self._filter_simple_lines(entry.get("bullets") or [])
        if not title and bullets:
            title = bullets[0] if len(bullets[0].split()) <= 8 else ""
            if title:
                bullets = bullets[1:]
        if not title:
            title = default_label
        if not bullets:
            return None
        return {"title": title, "subtitle": subtitle, "bullets": bullets}

    def _filter_simple_lines(self, values: list[Any]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            line = self._clean_display_text(value)
            if not line or self._looks_like_noise(line):
                continue
            if line.casefold() in {item.casefold() for item in cleaned}:
                continue
            cleaned.append(line)
        return cleaned[:4]

    def _clean_skill(self, value: Any) -> str | None:
        line = self._clean_display_text(value)
        if not line or self._looks_like_noise(line) or len(line) > 80:
            return None
        return line

    def _clean_display_text(self, value: Any) -> str:
        return " ".join(str(value or "").replace("???", " ").split()).strip(" -|	")

    def _looks_like_noise(self, value: str) -> bool:
        lowered = self._clean_display_text(value).lower()
        normalized = "".join(char if char.isalpha() or char == " " else "" for char in lowered).strip()
        if not lowered:
            return True
        if any(token in lowered for token in ["linkedin.com", "github.com", "http://", "https://", "@"]):
            return True
        return normalized in {"experience", "education", "certifications", "projects", "technical skills", "skills", "summary", "identity", "personal information"}

    def _page_line_breakdown(self, resume: dict[str, Any]) -> dict[str, int]:
        summary_lines = max(0, math.ceil(len(str(resume.get("summary") or "").split()) / 11)) if resume.get("summary") else 0
        experience_lines = sum(1 + len(entry.get("bullets") or []) for entry in (resume.get("experience") or []))
        project_lines = sum(1 + len(entry.get("bullets") or []) for entry in (resume.get("projects") or []))
        return {
            "summary_lines": summary_lines,
            "experience_lines": experience_lines,
            "project_lines": project_lines,
        }

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = str(value).strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result

    @staticmethod
    def render_resume_preview_html(resume: dict[str, Any], *, job_title: str, company: str) -> str:
        def render_entries(entries: list[dict[str, Any]]) -> str:
            parts: list[str] = []
            for entry in entries:
                title = escape(str(entry.get("title") or "Entry"))
                subtitle = escape(str(entry.get("subtitle") or ""))
                bullets = "".join(f"<li>{escape(str(bullet))}</li>" for bullet in entry.get("bullets") or [])
                subtitle_html = f"<p class='subhead'>{subtitle}</p>" if subtitle else ""
                parts.append(f"<article class='entry'><h4>{title}</h4>{subtitle_html}<ul>{bullets}</ul></article>")
            return "".join(parts)

        def render_section(title: str, inner_html: str) -> str:
            if not inner_html.strip():
                return ""
            return f"<section><div class='section-title'>{escape(title)}</div>{inner_html}</section>"

        identity = resume.get("identity") or {}
        identity_values = [escape(str(value)) for value in identity.values() if str(value or "").strip()]
        identity_line = " | ".join(identity_values)
        skills = "".join(f"<span>{escape(str(skill))}</span>" for skill in resume.get("skills") or [])
        certifications = "".join(f"<li>{escape(str(item))}</li>" for item in resume.get("certifications") or [])
        education = "".join(f"<li>{escape(str(item))}</li>" for item in resume.get("education") or [])
        page_plan = dict(resume.get("page_plan") or {})
        layout_blueprint = dict(page_plan.get("layout_blueprint") or {})
        spacing = dict(layout_blueprint.get("spacing_constraints") or {})
        font_scale = float(layout_blueprint.get("font_scale") or 1.0)
        section_gap = int(spacing.get("section_gap") or 8)
        line_height = float(spacing.get("line_height") or 1.18)
        summary_html = f"<p>{escape(str(resume.get('summary') or ''))}</p>" if str(resume.get("summary") or "").strip() else ""
        sections_html = "".join([
            render_section("Professional Summary", summary_html),
            render_section("Technical Skills", f"<div class='chips'>{skills}</div>" if skills else ""),
            render_section("Experience", render_entries(resume.get("experience") or [])),
            render_section("Projects", render_entries(resume.get("projects") or [])),
            render_section("Certifications", f"<ul>{certifications}</ul>" if certifications else ""),
            render_section("Education", f"<ul>{education}</ul>" if education else ""),
        ])
        name = escape(identity.get('full_name') or 'Tailored Resume')
        identity_html = f"<p class='identity'>{identity_line}</p>" if identity_line else ""
        return f"""
<!doctype html>
<html lang='en'>
  <head>
    <meta charset='utf-8'>
    <title>Resume Preview</title>
    <style>
      @page {{ size: A4; margin: 10mm; }}
      :root {{
        color-scheme: light;
        --font-scale: {font_scale:.3f};
        --section-gap: {section_gap}px;
        --line-height: {line_height:.2f};
      }}
      * {{ box-sizing: border-box; }}
      html, body {{ margin: 0; padding: 0; }}
      body {{ background:#f2efe9; color:#16120d; font-family:'Segoe UI',Arial,sans-serif; }}
      .sheet {{ width: 190mm; margin: 0 auto; background:#fff; }}
      .sheet-content {{ width:100%; }}
      .meta {{ display:flex; justify-content:space-between; font-size:calc(10px * var(--font-scale)); color:#67584b; letter-spacing:.06em; text-transform:uppercase; margin-bottom:6px; }}
      h1 {{ margin:0; font-size:calc(18px * var(--font-scale)); line-height:1.02; }}
      p {{ margin:0; line-height:var(--line-height); font-size:calc(11px * var(--font-scale)); }}
      .identity {{ margin-top:4px; color:#5d5147; font-size:calc(10.5px * var(--font-scale)); }}
      section {{ margin-top: var(--section-gap); }}
      .section-title {{ font-size:calc(8.75px * var(--font-scale)); letter-spacing:.18em; text-transform:uppercase; color:#9b5b20; margin-bottom:4px; font-weight:700; }}
      .chips {{ display:flex; flex-wrap:wrap; gap:4px; }}
      .chips span {{ border:1px solid #e8d6c4; border-radius:999px; padding:2px 8px; font-size:calc(10px * var(--font-scale)); background:#faf4ed; line-height:1.2; }}
      .entry {{ margin-bottom:6px; break-inside:avoid; }}
      .entry h4 {{ margin:0; font-size:calc(11.5px * var(--font-scale)); line-height:1.12; }}
      .subhead {{ font-size:calc(10px * var(--font-scale)); color:#6c5d52; margin-top:1px; }}
      ul {{ margin:4px 0 0 15px; padding:0; }}
      li {{ margin:2px 0; line-height:var(--line-height); font-size:calc(10.75px * var(--font-scale)); }}
      @media screen {{
        body {{ padding: 24px; }}
        .sheet {{ box-shadow:0 28px 60px rgba(16,12,8,.14); }}
      }}
      @media print {{
        body {{ background:#fff; }}
        .sheet {{ box-shadow:none; }}
      }}
    </style>
  </head>
  <body>
    <main class='sheet'>
      <div class='sheet-content'>
        <div class='meta'><span>{escape(job_title)}</span><span>{escape(company)}</span></div>
        <h1>{name}</h1>
        {identity_html}
        {sections_html}
      </div>
    </main>
  </body>
</html>
"""
