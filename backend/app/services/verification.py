from __future__ import annotations

import re
from typing import Any


class ResumeVerifierService:
    def verify(
        self,
        *,
        resume: dict[str, Any],
        evidence_pack: list[dict[str, Any]],
        requirement_profile: dict[str, Any],
        rendered_metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        repair_hints: list[dict[str, Any]] = []
        checks: dict[str, Any] = {}
        rendered_metrics = dict(rendered_metrics or {})
        evidence_text = "\n".join(str(item.get("text") or "") for item in evidence_pack)
        required_skills = {str(item).strip().casefold() for item in (requirement_profile.get("required_skills") or []) if str(item).strip()}
        generated_skills = {str(item).strip().casefold() for item in (resume.get("skills") or []) if str(item).strip()}
        keyword_coverage = len(required_skills & generated_skills) / max(len(required_skills), 1) if required_skills else 1.0
        checks["ats_keyword_coverage"] = round(keyword_coverage, 4)
        if keyword_coverage < 0.35 and required_skills:
            issues.append({"code": "low_keyword_coverage", "message": "ATS keyword coverage is weak for required skills."})
            repair_hints.append({"action": "prioritize_required_skills", "missing_skills": sorted(required_skills - generated_skills)[:6]})

        duplicate_bullets = self._duplicate_bullets(resume)
        checks["duplicate_bullets"] = duplicate_bullets
        if duplicate_bullets:
            issues.append({"code": "duplicate_bullets", "message": "Duplicate bullets were detected in the generated resume."})
            repair_hints.append({"action": "dedupe_bullets", "count": duplicate_bullets})

        chronology_ok, chronology_details = self._chronology_check(resume)
        checks["chronology_consistency"] = chronology_ok
        if not chronology_ok:
            issues.append({"code": "chronology_inconsistent", "message": "Experience chronology appears inconsistent.", "details": chronology_details})
            repair_hints.append({"action": "reorder_experience", "details": chronology_details})

        unsupported_claims = self._unsupported_claims(resume, evidence_text)
        checks["unsupported_claims"] = unsupported_claims
        if unsupported_claims:
            issues.append({"code": "unsupported_claims", "message": "Metrics or claims were detected without obvious evidence support.", "details": unsupported_claims[:6]})
            repair_hints.append({"action": "remove_or_rewrite_claims", "claims": unsupported_claims[:6]})

        estimated_lines = int((resume.get("page_plan") or {}).get("estimated_lines") or 0)
        rendered_pages = int(rendered_metrics.get("estimated_pages") or 1)
        overflow_px = int(rendered_metrics.get("overflow_px") or 0)
        render_overflow = estimated_lines > int((resume.get("page_plan") or {}).get("line_budget") or 52) or rendered_pages > 1 or overflow_px > 0
        checks["render_overflow_risk"] = {
            "overflow": render_overflow,
            "estimated_pages": rendered_pages,
            "overflow_px": overflow_px,
            "content_height_px": int(rendered_metrics.get("content_height_px") or 0),
            "printable_height_px": int(rendered_metrics.get("printable_height_px") or 0),
        }
        if render_overflow:
            issues.append({
                "code": "render_overflow",
                "message": "Render metrics indicate overflow risk for a single A4 page.",
                "details": checks["render_overflow_risk"],
            })
            repair_hints.append({
                "action": "shrink_sections",
                "suggestions": ["reduce experience bullets", "compress summary", "compact certifications"],
                "delta": {
                    "reduce_summary_lines": 1,
                    "compress_experience_titles": [entry.get("title") for entry in (resume.get("experience") or [])[-1:] if entry.get("title")],
                    "compress_project_titles": [entry.get("title") for entry in (resume.get("projects") or [])[-1:] if entry.get("title")],
                    "compact_certifications": True,
                    "trim_skills_to": 8,
                    "max_experience_bullets": 2,
                    "max_project_bullets": 2,
                },
            })

        section_balance = self._section_balance(resume, rendered_metrics)
        checks["section_balance"] = section_balance
        if not section_balance.get("balanced", True):
            issues.append({"code": "section_imbalance", "message": "The resume section balance is weak for one-page composition.", "details": section_balance})
            repair_hints.append({"action": "rebalance_sections", "details": section_balance, "delta": {"rebalance_sections": True}})

        validation_passed = not issues
        return {
            "passed": validation_passed,
            "issues": issues,
            "repair_hints": repair_hints,
            "checks": checks,
            "confidence": round(1.0 - min(len(issues) * 0.15, 0.8), 4),
        }

    def _duplicate_bullets(self, resume: dict[str, Any]) -> int:
        bullets: list[str] = []
        for section_name in ("experience", "projects"):
            for entry in (resume.get(section_name) or []):
                bullets.extend(str(item).strip().casefold() for item in (entry.get("bullets") or []) if str(item).strip())
        return len(bullets) - len(set(bullets))

    def _chronology_check(self, resume: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        year_sequences: list[int] = []
        for entry in (resume.get("experience") or []):
            subtitle = str(entry.get("subtitle") or "")
            found = [int(item) for item in re.findall(r"(?:19|20)\d{2}", subtitle)]
            if found:
                year_sequences.append(max(found))
        if len(year_sequences) < 2:
            return True, {"years": year_sequences}
        descending = year_sequences == sorted(year_sequences, reverse=True)
        return descending, {"years": year_sequences}

    def _unsupported_claims(self, resume: dict[str, Any], evidence_text: str) -> list[str]:
        claims: list[str] = []
        evidence_numbers = set(re.findall(r"\b\d+(?:%|\+)?\b", evidence_text))
        for section_name in ("experience", "projects"):
            for entry in (resume.get(section_name) or []):
                for bullet in (entry.get("bullets") or []):
                    text = str(bullet)
                    numbers = re.findall(r"\b\d+(?:%|\+)?\b", text)
                    if numbers and any(number not in evidence_numbers for number in numbers):
                        claims.append(text)
        return claims

    def _section_balance(self, resume: dict[str, Any], rendered_metrics: dict[str, Any]) -> dict[str, Any]:
        experience_count = len(resume.get("experience") or [])
        project_count = len(resume.get("projects") or [])
        skill_count = len(resume.get("skills") or [])
        white_space_ratio = float(rendered_metrics.get("white_space_ratio") or 0.0)
        balanced = experience_count >= 1 and skill_count >= 4 and project_count <= max(experience_count, 1) and white_space_ratio < 0.6
        return {
            "balanced": balanced,
            "experience_count": experience_count,
            "project_count": project_count,
            "skill_count": skill_count,
            "white_space_ratio": white_space_ratio,
        }
