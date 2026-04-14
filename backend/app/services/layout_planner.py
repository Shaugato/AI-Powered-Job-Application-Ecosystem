from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


class A4LayoutPlanner:
    def __init__(self, *, line_budget: int = 52) -> None:
        self.line_budget = line_budget

    def plan(self, resume: dict[str, Any], *, requirement_profile: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        requirement_profile = requirement_profile or {}
        planned = deepcopy(resume)
        decisions: list[str] = []
        section_priority = self._section_priority(planned, requirement_profile)
        section_budget = self._section_budget(section_priority)

        if planned.get("summary"):
            words = str(planned["summary"]).split()
            if len(words) > section_budget["summary_words"]:
                planned["summary"] = " ".join(words[: section_budget["summary_words"]])
                decisions.append("Summary compressed to the planner budget.")

        if len(planned.get("skills") or []) > section_budget["skill_count"]:
            planned["skills"] = list(planned.get("skills") or [])[: section_budget["skill_count"]]
            decisions.append("Technical skills reduced to the highest-priority keywords.")

        if len(planned.get("certifications") or []) > section_budget["certification_count"]:
            planned["certifications"] = list(planned.get("certifications") or [])[: section_budget["certification_count"]]
            decisions.append("Certifications compacted to preserve experience space.")

        if len(planned.get("education") or []) > section_budget["education_lines"]:
            planned["education"] = list(planned.get("education") or [])[: section_budget["education_lines"]]
            decisions.append("Education collapsed to the minimum required lines.")

        planned["experience"] = list(planned.get("experience") or [])[: section_budget["experience_entries"]]
        planned["projects"] = list(planned.get("projects") or [])[: section_budget["project_entries"]]

        for entry in planned.get("experience") or []:
            bullets = list(entry.get("bullets") or [])
            if len(bullets) > section_budget["experience_bullets"]:
                entry["bullets"] = bullets[: section_budget["experience_bullets"]]
                decisions.append(f"Experience bullets reduced in {entry.get('title') or 'experience'} to fit A4 constraints.")
        for entry in planned.get("projects") or []:
            bullets = list(entry.get("bullets") or [])
            if len(bullets) > section_budget["project_bullets"]:
                entry["bullets"] = bullets[: section_budget["project_bullets"]]
                decisions.append(f"Project bullets reduced in {entry.get('title') or 'project'} to protect whitespace balance.")

        while self._estimate_lines(planned) > self.line_budget:
            if not self._apply_line_overflow_reduction(planned, decisions, stage='planner overflow repair'):
                break

        estimated_lines = self._estimate_lines(planned)
        line_breakdown = self._line_breakdown(planned)
        compaction = dict(planned.get("_planner_compaction") or {})
        base_font_scale = 1.0 if estimated_lines <= self.line_budget - 4 else 0.98 if estimated_lines <= self.line_budget - 1 else 0.96
        font_scale = max(0.9, min(base_font_scale, float(compaction.get("font_scale") or 1.0)))
        spacing_mode = str(compaction.get("spacing_mode") or ("tight" if estimated_lines > self.line_budget - 4 else "balanced"))
        line_height = 1.18 if spacing_mode == 'tight' else 1.24
        section_gap = 7 if spacing_mode == 'tight' else 10
        layout_blueprint = {
            "section_priority": section_priority,
            "section_budget": section_budget,
            "line_budget": self.line_budget,
            "estimated_lines": estimated_lines,
            "font_scale": font_scale,
            "font_scale_bounds": [0.9, 1.0],
            "spacing_constraints": {"line_height": line_height, "section_gap": section_gap, "mode": spacing_mode},
            "widow_orphan_avoidance": True,
            "whitespace_balance": "compact" if spacing_mode == 'tight' else "balanced",
            "show_empty_sections": False,
            **line_breakdown,
        }
        planned["page_plan"] = {
            "paper_size": "A4",
            "target_pages": 1,
            "line_budget": self.line_budget,
            "estimated_lines": estimated_lines,
            "fits_on_one_page": estimated_lines <= self.line_budget,
            "decisions": decisions,
        }
        return planned, layout_blueprint, decisions

    def repair(self, resume: dict[str, Any], *, delta: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        planned = deepcopy(resume)
        decisions: list[str] = []
        compaction = dict(planned.get("_planner_compaction") or {})

        reduce_summary = int(delta.get("reduce_summary_lines") or 0)
        if reduce_summary and planned.get("summary"):
            words = str(planned["summary"]).split()
            trimmed = max(8, len(words) - 6 * reduce_summary)
            planned["summary"] = " ".join(words[:trimmed])
            decisions.append("Reduced summary from render feedback.")

        trim_skills_to = int(delta.get("trim_skills_to") or 0)
        if trim_skills_to and len(planned.get("skills") or []) > trim_skills_to:
            planned["skills"] = list(planned.get("skills") or [])[:trim_skills_to]
            decisions.append("Trimmed technical skills from structured repair feedback.")

        max_experience_bullets = int(delta.get("max_experience_bullets") or 0)
        if max_experience_bullets:
            for entry in planned.get("experience") or []:
                bullets = list(entry.get("bullets") or [])
                if len(bullets) > max_experience_bullets:
                    entry["bullets"] = bullets[:max_experience_bullets]
                    decisions.append(f"Compacted bullets in {entry.get('title') or 'experience'} from structured repair feedback.")

        max_project_bullets = int(delta.get("max_project_bullets") or 0)
        if max_project_bullets:
            for entry in planned.get("projects") or []:
                bullets = list(entry.get("bullets") or [])
                if len(bullets) > max_project_bullets:
                    entry["bullets"] = bullets[:max_project_bullets]
                    decisions.append(f"Compacted bullets in {entry.get('title') or 'project'} from structured repair feedback.")

        for target in delta.get("compress_experience_titles") or []:
            for entry in planned.get("experience") or []:
                if entry.get("title") == target and len(entry.get("bullets") or []) > 1:
                    entry["bullets"] = list(entry.get("bullets") or [])[:-1]
                    decisions.append(f"Compressed bullets for {target} from render feedback.")

        for target in delta.get("compress_project_titles") or []:
            for entry in planned.get("projects") or []:
                if entry.get("title") == target and len(entry.get("bullets") or []) > 1:
                    entry["bullets"] = list(entry.get("bullets") or [])[:-1]
                    decisions.append(f"Compressed bullets for {target} from render feedback.")

        if delta.get("compact_certifications") and len(planned.get("certifications") or []) > 1:
            planned["certifications"] = list(planned.get("certifications") or [])[:1]
            decisions.append("Compacted certifications from render feedback.")

        if delta.get("compact_education") and len(planned.get("education") or []) > 1:
            planned["education"] = list(planned.get("education") or [])[:1]
            decisions.append("Compacted education from render feedback.")

        if delta.get("remove_last_project") and planned.get("projects"):
            planned["projects"] = list(planned.get("projects") or [])[:-1]
            decisions.append("Removed the lowest-priority project from render feedback.")

        if delta.get("remove_last_experience") and len(planned.get("experience") or []) > 2:
            planned["experience"] = list(planned.get("experience") or [])[:-1]
            decisions.append("Removed the lowest-priority experience entry from render feedback.")

        if delta.get("drop_summary") and planned.get("summary"):
            planned["summary"] = None
            decisions.append("Removed the summary from render feedback.")

        if delta.get("reorder_experience"):
            planned["experience"] = self._sort_experience_entries(list(planned.get("experience") or []))
            decisions.append("Reordered experience entries to restore chronology consistency.")

        if delta.get("rebalance_sections"):
            while len(planned.get("projects") or []) > max(len(planned.get("experience") or []), 1):
                planned["projects"] = list(planned.get("projects") or [])[:-1]
                decisions.append("Reduced projects to rebalance the one-page layout.")
            if len(planned.get("skills") or []) > 8:
                planned["skills"] = list(planned.get("skills") or [])[:8]
                decisions.append("Reduced the skill list to rebalance the layout.")

        tighten_steps = int(delta.get("tighten_spacing_steps") or 0)
        if tighten_steps:
            current_scale = float(compaction.get("font_scale") or 1.0)
            compaction["font_scale"] = max(0.9, current_scale - (0.02 * tighten_steps))
            compaction["spacing_mode"] = "tight"
            decisions.append("Tightened font scale and spacing from measured render feedback.")

        if compaction:
            planned["_planner_compaction"] = compaction

        while self._estimate_lines(planned) > self.line_budget:
            if not self._apply_line_overflow_reduction(planned, decisions, stage='final repair enforcement'):
                break
        return planned, decisions

    def _section_priority(self, resume: dict[str, Any], requirement_profile: dict[str, Any]) -> dict[str, float]:
        required = {str(item).strip().casefold() for item in requirement_profile.get("required_skills") or [] if str(item).strip()}
        skill_overlap = len({str(item).strip().casefold() for item in resume.get("skills") or []} & required)
        return {
            "identity": 1.0,
            "summary": 0.62 if resume.get("summary") else 0.0,
            "technical_skills": 0.84 + min(skill_overlap * 0.01, 0.08),
            "experience": 1.0,
            "projects": 0.72,
            "certifications": 0.55 + (0.05 if requirement_profile.get("certifications") else 0.0),
            "education": 0.38,
        }

    def _section_budget(self, section_priority: dict[str, float]) -> dict[str, int]:
        return {
            "summary_words": 34 if section_priority.get("summary", 0.0) >= 0.6 else 24,
            "skill_count": 10,
            "experience_entries": 3,
            "experience_bullets": 3,
            "project_entries": 2,
            "project_bullets": 2,
            "certification_count": 3,
            "education_lines": 2,
        }

    def _estimate_lines(self, resume: dict[str, Any]) -> int:
        lines = 2
        identity = resume.get("identity") or {}
        if any(str(value or "").strip() for value in identity.values()):
            lines += 1
        if resume.get("summary"):
            lines += max(1, math.ceil(len(str(resume.get("summary") or "").split()) / 12))
        if resume.get("skills"):
            lines += 1 + math.ceil(len(resume.get("skills") or []) / 7)
        for section_name in ("experience", "projects"):
            entries = resume.get(section_name) or []
            if entries:
                lines += 1
            for entry in entries:
                lines += 1 + len(entry.get("bullets") or [])
                if entry.get("subtitle"):
                    lines += 1
        if resume.get("certifications"):
            lines += 1 + math.ceil(len(resume.get("certifications") or []) / 4)
        if resume.get("education"):
            lines += 1 + len(resume.get("education") or [])
        return lines

    def _line_breakdown(self, resume: dict[str, Any]) -> dict[str, int]:
        summary_lines = max(0, math.ceil(len(str(resume.get("summary") or "").split()) / 12)) if resume.get("summary") else 0
        experience_lines = sum(1 + len(entry.get("bullets") or []) + (1 if entry.get("subtitle") else 0) for entry in (resume.get("experience") or []))
        project_lines = sum(1 + len(entry.get("bullets") or []) + (1 if entry.get("subtitle") else 0) for entry in (resume.get("projects") or []))
        return {
            "summary_lines": summary_lines,
            "experience_lines": experience_lines,
            "project_lines": project_lines,
        }

    def _sort_experience_entries(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def key(entry: dict[str, Any]) -> tuple[int, str]:
            subtitle = str(entry.get("subtitle") or "")
            years = [int(item) for item in __import__("re").findall(r"(?:19|20)\d{2}", subtitle)]
            return (max(years) if years else 0, str(entry.get("title") or ""))
        return sorted(entries, key=key, reverse=True)

    def _apply_line_overflow_reduction(self, planned: dict[str, Any], decisions: list[str], *, stage: str) -> bool:
        if planned.get("projects"):
            last = planned["projects"][-1]
            if len(last.get("bullets") or []) > 1:
                last["bullets"] = list(last["bullets"] or [])[:-1]
                decisions.append(f"Removed one project bullet from {last.get('title') or 'project'} during {stage}.")
                return True
            planned["projects"] = list(planned.get("projects") or [])[:-1]
            decisions.append(f"Removed the lowest-priority project during {stage}.")
            return True
        if planned.get("summary") and len(str(planned["summary"]).split()) > 12:
            planned["summary"] = " ".join(str(planned["summary"]).split()[:-4])
            decisions.append(f"Reduced summary during {stage}.")
            return True
        if planned.get("skills") and len(planned["skills"]) > 6:
            planned["skills"] = list(planned.get("skills") or [])[:-1]
            decisions.append(f"Removed one lower-priority skill during {stage}.")
            return True
        if planned.get("certifications") and len(planned["certifications"]) > 1:
            planned["certifications"] = list(planned.get("certifications") or [])[:-1]
            decisions.append(f"Removed one certification during {stage}.")
            return True
        if planned.get("education") and len(planned["education"]) > 1:
            planned["education"] = list(planned.get("education") or [])[:1]
            decisions.append(f"Compacted education during {stage}.")
            return True
        if planned.get("experience"):
            last = planned["experience"][-1]
            if len(last.get("bullets") or []) > 1:
                last["bullets"] = list(last.get("bullets") or [])[:-1]
                decisions.append(f"Removed one experience bullet from {last.get('title') or 'experience'} during {stage}.")
                return True
            if len(planned.get("experience") or []) > 2:
                planned["experience"] = list(planned.get("experience") or [])[:-1]
                decisions.append(f"Removed the lowest-priority experience entry during {stage}.")
                return True
        return False
