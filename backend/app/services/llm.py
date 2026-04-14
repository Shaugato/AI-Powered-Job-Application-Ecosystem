from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from openai import OpenAI
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.entities import IntegrationConnection

EMBEDDING_DIMENSION = 3072
PROFILE_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "full_name": {"type": ["string", "null"]},
        "email": {"type": ["string", "null"]},
        "phone": {"type": ["string", "null"]},
        "location": {"type": ["string", "null"]},
        "website": {"type": ["string", "null"]},
        "summary": {"type": ["string", "null"]},
        "skills": {"type": "array", "items": {"type": "string"}},
        "certifications": {"type": "array", "items": {"type": "string"}},
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
        "education": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["full_name", "email", "phone", "location", "website", "summary", "skills", "certifications", "experience", "projects", "education"],
}
DOCUMENT_CLEAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "normalized_text": {"type": "string"},
    },
    "required": ["normalized_text"],
}
JOB_REQUIREMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "role_family": {"type": ["string", "null"]},
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "preferred_skills": {"type": "array", "items": {"type": "string"}},
        "certifications": {"type": "array", "items": {"type": "string"}},
        "location_signals": {"type": "array", "items": {"type": "string"}},
        "work_mode": {"type": ["string", "null"]},
        "seniority": {"type": ["string", "null"]},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "role_family",
        "required_skills",
        "preferred_skills",
        "certifications",
        "location_signals",
        "work_mode",
        "seniority",
        "risk_flags",
    ],
}
COMMON_SKILLS_PATTERN = re.compile(
    r"\b(AWS|Azure|GCP|Python|Terraform|Docker|Kubernetes|Linux|Networking|Security|CCNA|CI/CD|GitHub|Git|PowerShell|Windows|VMware|Active Directory|Office 365|M365|Splunk|SIEM)\b",
    re.I,
)
COMMON_CERT_PATTERN = re.compile(r"\b(CCNA|Security\+|CISSP|ITIL|AWS Certified [A-Za-z ]+)\b", re.I)
SECTION_WORDS = {
    "experience",
    "education",
    "certifications",
    "projects",
    "skills",
    "summary",
    "profile",
    "contact",
    "github",
    "linkedin",
    "phone",
    "email",
}
DOCUMENT_AI_CONNECTION_KEYS = ("openai_ai", "gemini_ai")
CONTACT_TOKEN_PATTERN = re.compile(r"@|linkedin\.com|github\.com|https?://|www\.|(?:\+?\d[\d\s()./-]{7,})", re.I)
SECTION_HEADING_VALUES = {
    "experience",
    "work experience",
    "professional experience",
    "employment history",
    "education",
    "certifications",
    "projects",
    "technical skills",
    "skills",
    "summary",
    "profile",
    "contact",
    "references",
}
GENERIC_DOCUMENT_TOKENS = {"resume", "cv", "curriculum vitae", "document", "cover letter", "prompt"}


def _prepare_structured_text(text: str, *, max_chars: int = 12000) -> str:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    lines = [re.sub(r"\s+", " ", line).strip(" |\t") for line in normalized.split("\n")]
    cleaned_lines: list[str] = []
    previous: str | None = None
    for line in lines:
        if not line:
            if previous != "":
                cleaned_lines.append("")
            previous = ""
            continue
        if line == previous:
            continue
        cleaned_lines.append(line)
        previous = line
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned[:max_chars]


def _clean_scalar(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" -|\t")


def _strip_bullet_prefix(value: str) -> str:
    return re.sub(r"^(?:[-*?]+|\d+[.)])\s*", "", value).strip()


def _looks_like_contact_line(value: str) -> bool:
    text = _clean_scalar(value)
    return bool(text and CONTACT_TOKEN_PATTERN.search(text))


def _looks_like_heading(value: str) -> bool:
    text = _clean_scalar(value)
    normalized = re.sub(r"[^a-z ]", "", text.lower()).strip()
    if not normalized:
        return False
    if normalized in SECTION_HEADING_VALUES or normalized in SECTION_WORDS:
        return True
    return text.isupper() and len(normalized.split()) <= 4 and normalized in SECTION_HEADING_VALUES


def _clean_skill_value(value: Any) -> str | None:
    text = _clean_scalar(value)
    if not text:
        return None
    if _looks_like_heading(text) or _looks_like_contact_line(text):
        return None
    if text.lower().endswith(".txt") or len(text) > 80:
        return None
    return text


def _sanitize_entry_list(entries: list[dict[str, Any]] | None, *, label: str, limit: int) -> list[dict[str, Any]]:
    cleaned_entries: list[dict[str, Any]] = []
    for index, raw_entry in enumerate(entries or [], start=1):
        title = _clean_scalar((raw_entry or {}).get("title"))
        subtitle = _clean_scalar((raw_entry or {}).get("subtitle")) or None
        bullets = [_strip_bullet_prefix(_clean_scalar(item)) for item in ((raw_entry or {}).get("bullets") or [])]
        bullets = [
            bullet
            for bullet in bullets
            if bullet
            and not _looks_like_heading(bullet)
            and not _looks_like_contact_line(bullet)
            and bullet.casefold() not in {title.casefold() if title else "", subtitle.casefold() if subtitle else ""}
        ]
        bullets = _dedupe(bullets)[:4]

        normalized_title = title.lower()
        if title and (_looks_like_heading(title) or _looks_like_contact_line(title) or any(token in normalized_title for token in GENERIC_DOCUMENT_TOKENS)):
            title = ""
        if subtitle and (_looks_like_heading(subtitle) or _looks_like_contact_line(subtitle)):
            subtitle = None
        if not title and subtitle:
            title, subtitle = subtitle, None
        if not title and bullets:
            candidate = bullets[0]
            if len(candidate.split()) <= 8 and not _looks_like_contact_line(candidate):
                title = candidate
                bullets = bullets[1:]
        if not title:
            title = f"{label} {index}"
        if not bullets:
            continue
        cleaned_entries.append({"title": title, "subtitle": subtitle, "bullets": bullets})
        if len(cleaned_entries) >= limit:
            break
    return cleaned_entries


def _sanitize_candidate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    full_name = _clean_scalar(profile.get("full_name")) or None
    if full_name and (_looks_like_heading(full_name) or any(char.isdigit() for char in full_name) or "resume" in full_name.lower()):
        full_name = None
    email = _clean_scalar(profile.get("email")) or None
    phone = _clean_scalar(profile.get("phone")) or None
    location = _clean_scalar(profile.get("location")) or None
    website = _clean_scalar(profile.get("website")) or None
    summary = _clean_scalar(profile.get("summary")) or None
    if summary and (_looks_like_contact_line(summary) or _looks_like_heading(summary) or summary.isupper()):
        summary = None
    if summary and len(summary.split()) > 48:
        summary = " ".join(summary.split()[:48])

    skills = _dedupe([item for item in (_clean_skill_value(value) for value in (profile.get("technical_skills") or profile.get("skills") or [])) if item])[:18]
    certifications = _dedupe([
        item
        for item in (_clean_skill_value(value) for value in (profile.get("certifications") or []))
        if item and item.lower() not in {"certifications", "certificate"}
    ])[:10]
    education = _dedupe([
        line
        for line in (_clean_scalar(value) for value in (profile.get("education") or []))
        if line and not _looks_like_heading(line) and not _looks_like_contact_line(line)
    ])[:4]

    return {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "location": location,
        "website": website,
        "summary": summary,
        "skills": skills,
        "technical_skills": skills,
        "certifications": certifications,
        "experience": _sanitize_entry_list(profile.get("experience") or [], label="Experience", limit=6),
        "projects": _sanitize_entry_list(profile.get("projects") or [], label="Project", limit=4),
        "education": education,
    }



class LLMProvider(Protocol):
    def generate_json(self, *, model: str, instructions: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


class DocumentAIProvider(Protocol):
    def normalize_document_text(self, *, text: str, file_name: str | None = None, file_path: str | Path | None = None) -> str:
        ...

    def extract_candidate_profile_from_texts(self, texts: list[str]) -> dict[str, Any]:
        ...


@dataclass
class DocumentAIRuntime:
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    parser_model: str | None = None


def _dedupe(values: list[str]) -> list[str]:
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


def _first_match(pattern: str, text: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    return match.group(1).strip() if match.groups() else match.group(0).strip()


def _estimate_resume_lines(resume: dict[str, Any]) -> int:
    lines = 4
    summary_words = len(str(resume.get('summary') or '').split())
    if summary_words:
        lines += max(2, math.ceil(summary_words / 11))
    if resume.get('skills'):
        lines += 2 + math.ceil(len(resume['skills']) / 6)
    for section_name in ('experience', 'projects'):
        section = resume.get(section_name) or []
        if section:
            lines += 1
        for entry in section:
            bullets = entry.get('bullets') or []
            lines += 1 + len(bullets)
    if resume.get('certifications'):
        lines += 1 + math.ceil(len(resume['certifications']) / 3)
    if resume.get('education'):
        lines += 1 + len(resume['education'])
    return lines


def _compress_resume(resume: dict[str, Any], line_budget: int = 52) -> dict[str, Any]:
    decisions: list[str] = []
    summary = str(resume.get('summary') or '').strip()
    if len(summary.split()) > 34:
        resume['summary'] = ' '.join(summary.split()[:34])
        decisions.append('Summary compressed to preserve one-page layout.')

    if len(resume.get('skills') or []) > 12:
        resume['skills'] = resume['skills'][:12]
        decisions.append('Skill list trimmed to the highest-signal items.')

    for section_name in ('projects', 'experience'):
        section = resume.get(section_name) or []
        max_entries = 2 if section_name == 'projects' else 4
        if len(section) > max_entries:
            resume[section_name] = section[:max_entries]
            decisions.append(f'{section_name.title()} trimmed to fit the page.')
        for entry in resume.get(section_name) or []:
            bullets = entry.get('bullets') or []
            if len(bullets) > 3:
                entry['bullets'] = bullets[:3]
                decisions.append(f"{entry.get('title') or section_name.title()} limited to three bullets.")

    estimated = _estimate_resume_lines(resume)
    if estimated > line_budget:
        for section_name in ('projects', 'experience'):
            for entry in resume.get(section_name) or []:
                bullets = entry.get('bullets') or []
                if len(bullets) > 2 and estimated > line_budget:
                    entry['bullets'] = bullets[:2]
                    estimated = _estimate_resume_lines(resume)
                    decisions.append(f"Reduced bullets for {entry.get('title') or section_name} to stay within one page.")

    estimated = _estimate_resume_lines(resume)
    resume['page_plan'] = {
        'paper_size': 'A4',
        'target_pages': 1,
        'line_budget': line_budget,
        'estimated_lines': estimated,
        'fits_on_one_page': estimated <= line_budget,
        'decisions': _dedupe(decisions),
    }
    return resume


def heuristic_generate_application(payload: dict[str, Any]) -> dict[str, Any]:
    job = payload['job']
    evidence = payload.get('evidence') or []
    candidate = payload.get('candidate_profile') or {}

    evidence_bullets = [item['text'] for item in evidence if item.get('text')]
    skills = _dedupe(list(candidate.get('skills') or []) + [skill for item in evidence for skill in item.get('skills', [])])[:14]
    experience = list(candidate.get('experience') or [])
    if not experience:
        experience = [{
            'title': 'Relevant Experience',
            'subtitle': None,
            'bullets': evidence_bullets[:4] or [f"Delivered work aligned to {job['title']} requirements."],
        }]
    projects = list(candidate.get('projects') or [])[:2]
    certifications = _dedupe(list(candidate.get('certifications') or []))[:6]
    education = _dedupe(list(candidate.get('education') or []))[:3]
    summary = str(candidate.get('summary') or '').strip() or f"Targeting {job['title']} opportunities with grounded experience across {', '.join(job.get('labels', [])[:3]) or 'technology operations'} and evidence-backed delivery."

    resume = {
        'summary': summary,
        'skills': skills,
        'experience': experience,
        'projects': projects,
        'certifications': certifications,
        'education': education,
        'page_plan': {},
    }
    resume = _compress_resume(resume)

    key_points = evidence_bullets[:3] or [summary]
    cover_letter = {
        'opening': f"I am applying for the {job['title']} role at {job['company']}",
        'body_paragraphs': [
            f"My background aligns with the role's priorities in {', '.join(job.get('labels', [])[:3]) or 'platform, cloud, and infrastructure delivery'}.",
            f"I would bring evidence-backed results such as {key_points[0]}." if key_points else "I would bring grounded, role-relevant evidence from prior work.",
        ],
        'closing': 'Thank you for your time and consideration.',
    }
    return {'resume': resume, 'cover_letter': cover_letter}


def heuristic_extract_candidate_profile(texts: list[str]) -> dict[str, Any]:
    combined = "\n".join(texts)
    lines = [re.sub(r"\s+", " ", line).strip(" -|\t") for line in combined.splitlines() if line.strip()]

    full_name = None
    for line in lines[:12]:
        candidate = re.sub(r"[^A-Za-z .'-]", " ", line)
        candidate = re.sub(r"\s+", " ", candidate).strip()
        words = [word for word in candidate.split() if word]
        if not (2 <= len(words) <= 4):
            continue
        if any(word.casefold() in SECTION_WORDS for word in words):
            continue
        if any(char.isdigit() for char in candidate):
            continue
        if sum(char.isalpha() for char in candidate) < 6:
            continue
        full_name = candidate.title() if candidate.isupper() else candidate
        break

    email = _first_match(r"([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", combined, re.I)
    phone = _first_match(r"((?:\+?61|0)\s?\d(?:[\s-]?\d){8,})", combined)
    location = _first_match(r"((?:Melbourne|Sydney|Brisbane|Perth|Adelaide|Canberra|Hobart|Geelong)(?:,\s*(?:VIC|NSW|QLD|WA|SA|ACT|TAS))?)", combined, re.I)
    if not location:
        location = _first_match(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2},\s*(?:VIC|NSW|QLD|WA|SA|ACT|TAS))", combined)

    websites = re.findall(r"(https?://[^\s)]+|www\.[^\s)]+|linkedin\.com/[^\s)]+|github\.com/[^\s)]+)", combined, re.I)
    website = None
    if websites:
        website = websites[0].strip()
        if website.startswith("www."):
            website = f"https://{website}"
        if website.startswith("linkedin.com") or website.startswith("github.com"):
            website = f"https://{website}"

    paragraphs = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\n\s*\n", combined) if part.strip()]
    summary = next(
        (
            part
            for part in paragraphs
            if len(part.split()) >= 12
            and "@" not in part
            and "linkedin.com" not in part.lower()
            and "github.com" not in part.lower()
            and not part.isupper()
        ),
        None,
    )
    if summary and len(summary.split()) > 40:
        summary = " ".join(summary.split()[:40])

    skills = _dedupe([match.upper() if match.isupper() else match.title() for match in COMMON_SKILLS_PATTERN.findall(combined)])[:18]
    certifications = _dedupe([match.upper() if match.isupper() else match for match in COMMON_CERT_PATTERN.findall(combined)])[:8]

    return {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "location": location,
        "website": website,
        "summary": summary,
        "skills": skills,
        "technical_skills": skills,
        "certifications": certifications,
        "experience": [],
        "projects": [],
        "education": [],
    }


@dataclass
class NullLLMProvider:
    def generate_json(self, *, model: str, instructions: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        return heuristic_generate_application(payload)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embed(text) for text in texts]


class OpenAIResponsesProvider:
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self.settings = settings
        self.client = OpenAI(api_key=api_key or settings.openai_api_key, base_url=base_url or settings.openai_base_url)

    def generate_json(self, *, model: str, instructions: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        response = self.client.responses.create(
            model=model,
            instructions=instructions,
            input=json.dumps(payload),
            text={
                'format': {
                    'type': 'json_schema',
                    'name': 'grounded_job_application',
                    'strict': True,
                    'schema': schema,
                }
            },
        )
        return json.loads(response.output_text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.settings.openai_embedding_model,
            input=texts,
        )
        return [row.embedding for row in response.data]


class NullDocumentAIProvider:
    def normalize_document_text(self, *, text: str, file_name: str | None = None, file_path: str | Path | None = None) -> str:
        return text

    def extract_candidate_profile_from_texts(self, texts: list[str]) -> dict[str, Any]:
        return heuristic_extract_candidate_profile(texts)


class OpenAIDocumentProvider:
    def __init__(self, runtime: DocumentAIRuntime) -> None:
        settings = get_settings()
        self.settings = settings
        self.model = runtime.parser_model or settings.openai_parser_model
        self.client = OpenAI(api_key=runtime.api_key, base_url=runtime.base_url or settings.openai_base_url)

    def generate_json(self, *, instructions: str, payload: dict[str, Any], schema: dict[str, Any], schema_name: str) -> dict[str, Any]:
        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=json.dumps(payload),
            text={
                'format': {
                    'type': 'json_schema',
                    'name': schema_name,
                    'strict': True,
                    'schema': schema,
                }
            },
        )
        return json.loads(response.output_text)

    def normalize_document_text(self, *, text: str, file_name: str | None = None, file_path: str | Path | None = None) -> str:
        cleaned = _prepare_structured_text(text, max_chars=14000)
        if not cleaned:
            return ""
        instructions = (
            "You will receive a resume, CV, cover letter, or prompt-history document. "
            "Rewrite it into clean ATS-friendly plain text without inventing information. "
            "Preserve headings, line breaks, role boundaries, and bullet lists whenever they can be inferred. "
            "Do not collapse the document into one paragraph. Repair broken separators and OCR issues."
        )
        if file_path:
            path = Path(file_path)
            if path.exists() and path.suffix.lower() == ".pdf" and path.stat().st_size <= 18 * 1024 * 1024:
                encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
                response = self.client.responses.create(
                    model=self.model,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_file",
                                    "filename": path.name,
                                    "file_data": f"data:application/pdf;base64,{encoded}",
                                },
                                {"type": "input_text", "text": instructions},
                                {"type": "input_text", "text": f"Fallback extracted text:\n{cleaned}"},
                            ],
                        }
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "document_clean",
                            "strict": True,
                            "schema": DOCUMENT_CLEAN_SCHEMA,
                        }
                    },
                )
                normalized = _prepare_structured_text(str(json.loads(response.output_text).get("normalized_text") or ""), max_chars=14000)
                if normalized:
                    return normalized
        result = self.generate_json(
            instructions=instructions,
            payload={"file_name": file_name, "text": cleaned},
            schema=DOCUMENT_CLEAN_SCHEMA,
            schema_name="document_clean",
        )
        return _prepare_structured_text(str(result.get("normalized_text") or ""), max_chars=14000) or cleaned

    def extract_candidate_profile_from_texts(self, texts: list[str]) -> dict[str, Any]:
        cleaned = [_prepare_structured_text(text, max_chars=9000) for text in texts if str(text).strip()]
        profile = self.generate_json(
            instructions=(
                "Extract a truthful candidate profile from uploaded resumes, CVs, cover letters, and prompt notes. "
                "Keep the response grounded to the source only. Return clean ATS-friendly wording. "
                "Identify the candidate's real identity, summary, technical skills, certifications, education, projects, and work experience. "
                "Each work experience entry must use a clean role title, a subtitle with employer and dates when available, and concise factual bullets. "
                "Never place contact details, links, headings, file names, or section labels inside experience or project bullets. "
                "Return null instead of guessing when a field is unclear."
            ),
            payload={"documents": cleaned[:8]},
            schema=PROFILE_EXTRACTION_SCHEMA,
            schema_name="candidate_profile",
        )
        return _sanitize_candidate_profile(profile)


class GeminiDocumentProvider:
    def __init__(self, runtime: DocumentAIRuntime) -> None:
        settings = get_settings()
        self.settings = settings
        self.model = runtime.parser_model or settings.gemini_parser_model
        self.base_url = (runtime.base_url or settings.gemini_base_url).rstrip("/")
        self.api_key = runtime.api_key or ""

    def _request_json(self, body: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/models/{self.model}:generateContent",
            params={"key": self.api_key},
            json=body,
            timeout=45,
        )
        response.raise_for_status()
        return response.json()

    def _response_text(self, payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        chunks = [str(part.get("text") or "") for part in parts if part.get("text")]
        text = "\n".join(chunk for chunk in chunks if chunk).strip()
        if not text:
            raise RuntimeError("Gemini returned an empty text payload")
        return text

    def generate_json(self, *, instructions: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
        body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                f"{instructions}\n\n"
                                "Return JSON only.\n\n"
                                f"Payload:\n{json.dumps(payload, ensure_ascii=False)}"
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        return json.loads(self._response_text(self._request_json(body)))

    def normalize_document_text(self, *, text: str, file_name: str | None = None, file_path: str | Path | None = None) -> str:
        cleaned = _prepare_structured_text(text, max_chars=14000)
        if not cleaned:
            return ""
        instructions = (
            "Rewrite this career document into clean ATS-friendly plain text. "
            "Preserve headings, role boundaries, and bullet structure wherever possible. "
            "Preserve only factual information from the source and repair broken separators or line wraps."
        )
        parts: list[dict[str, Any]] = []
        if file_path:
            path = Path(file_path)
            if path.exists() and path.suffix.lower() == ".pdf" and path.stat().st_size <= 18 * 1024 * 1024:
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": base64.b64encode(path.read_bytes()).decode("utf-8"),
                        }
                    }
                )
        parts.append({"text": f"{instructions}\n\nFile name: {file_name or 'document'}\n\nFallback extracted text:\n{cleaned}"})
        body = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": DOCUMENT_CLEAN_SCHEMA,
            },
        }
        result = json.loads(self._response_text(self._request_json(body)))
        return _prepare_structured_text(str(result.get("normalized_text") or ""), max_chars=14000) or cleaned

    def extract_candidate_profile_from_texts(self, texts: list[str]) -> dict[str, Any]:
        cleaned = [_prepare_structured_text(text, max_chars=9000) for text in texts if str(text).strip()]
        profile = self.generate_json(
            instructions=(
                "Extract a truthful candidate profile from resumes, CVs, cover letters, and prompt notes. "
                "Do not invent information. Return clean ATS-friendly wording. "
                "Return distinct technical skills, certifications, education lines, project entries, and work experience entries. "
                "Each work experience entry must use a clean role title, a subtitle with employer and dates when available, and concise bullets only."
            ),
            payload={"documents": cleaned[:8]},
            schema=PROFILE_EXTRACTION_SCHEMA,
        )
        return _sanitize_candidate_profile(profile)


def _hash_embed(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    tokens = [token for token in text.lower().split() if token]
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode('utf-8')).digest()
        for offset in range(0, 12, 4):
            index = int.from_bytes(digest[offset : offset + 4], 'big') % EMBEDDING_DIMENSION
            sign = 1.0 if digest[offset] % 2 == 0 else -1.0
            vector[index] += sign

    norm = math.sqrt(sum(component * component for component in vector)) or 1.0
    return [round(component / norm, 6) for component in vector]


def _ai_connection_candidates(db: Session | None) -> list[IntegrationConnection]:
    if db is None:
        return []
    return (
        db.query(IntegrationConnection)
        .filter(IntegrationConnection.provider_key.in_(DOCUMENT_AI_CONNECTION_KEYS))
        .order_by(IntegrationConnection.updated_at.desc())
        .all()
    )


def _runtime_from_connection(connection: IntegrationConnection) -> DocumentAIRuntime | None:
    settings_json = connection.settings_json or {}
    secrets_json = connection.secrets_json or {}
    api_key = str(secrets_json.get("api_key") or "").strip()
    if not api_key:
        return None
    if connection.provider_key == "openai_ai":
        return DocumentAIRuntime(
            provider="openai",
            api_key=api_key,
            base_url=str(settings_json.get("base_url") or get_settings().openai_base_url).strip() or None,
            parser_model=str(settings_json.get("parser_model") or get_settings().openai_parser_model).strip() or None,
        )
    if connection.provider_key == "gemini_ai":
        return DocumentAIRuntime(
            provider="gemini",
            api_key=api_key,
            base_url=str(settings_json.get("base_url") or get_settings().gemini_base_url).strip() or None,
            parser_model=str(settings_json.get("parser_model") or get_settings().gemini_parser_model).strip() or None,
        )
    return None


def resolve_openai_generation_runtime(db: Session | None = None) -> DocumentAIRuntime | None:
    settings = get_settings()
    for connection in _ai_connection_candidates(db):
        runtime = _runtime_from_connection(connection)
        if runtime and runtime.provider == "openai":
            return runtime
    if settings.openai_api_key:
        return DocumentAIRuntime("openai", settings.openai_api_key, settings.openai_base_url, settings.openai_parser_model)
    return None


def resolve_document_ai_runtime(db: Session | None = None) -> DocumentAIRuntime:
    settings = get_settings()
    explicit = settings.document_ai_provider.strip().lower()
    connections = _ai_connection_candidates(db)

    def pick_connection(provider_name: str) -> DocumentAIRuntime | None:
        for connection in connections:
            runtime = _runtime_from_connection(connection)
            if runtime and runtime.provider == provider_name:
                return runtime
        return None

    if explicit in {"openai", "gemini"}:
        runtime = pick_connection(explicit)
        if runtime:
            return runtime
        if explicit == "openai" and settings.openai_api_key:
            return DocumentAIRuntime("openai", settings.openai_api_key, settings.openai_base_url, settings.openai_parser_model)
        if explicit == "gemini" and settings.gemini_api_key:
            return DocumentAIRuntime("gemini", settings.gemini_api_key, settings.gemini_base_url, settings.gemini_parser_model)
        return DocumentAIRuntime("null")

    for connection in connections:
        runtime = _runtime_from_connection(connection)
        if runtime:
            return runtime
    if settings.openai_api_key:
        return DocumentAIRuntime("openai", settings.openai_api_key, settings.openai_base_url, settings.openai_parser_model)
    if settings.gemini_api_key:
        return DocumentAIRuntime("gemini", settings.gemini_api_key, settings.gemini_base_url, settings.gemini_parser_model)
    return DocumentAIRuntime("null")


def get_document_ai_provider(db: Session | None = None) -> DocumentAIProvider:
    runtime = resolve_document_ai_runtime(db)
    if runtime.provider == "openai" and runtime.api_key:
        return OpenAIDocumentProvider(runtime)
    if runtime.provider == "gemini" and runtime.api_key:
        return GeminiDocumentProvider(runtime)
    return NullDocumentAIProvider()


def normalize_document_text(text: str, *, file_name: str | None = None, file_path: str | Path | None = None, db: Session | None = None) -> str:
    cleaned = _prepare_structured_text(text, max_chars=14000)
    if not cleaned:
        return ""
    provider = get_document_ai_provider(db)
    try:
        normalized = provider.normalize_document_text(text=cleaned, file_name=file_name, file_path=file_path)
        return _prepare_structured_text(normalized or cleaned, max_chars=14000) or cleaned
    except Exception:
        return cleaned


def extract_candidate_profile_from_texts(texts: list[str], *, db: Session | None = None) -> dict[str, Any]:
    cleaned = [_prepare_structured_text(text, max_chars=9000) for text in texts if str(text).strip()]
    if not cleaned:
        return {
            "full_name": None,
            "email": None,
            "phone": None,
            "location": None,
            "website": None,
            "summary": None,
            "skills": [],
            "technical_skills": [],
            "certifications": [],
            "experience": [],
            "projects": [],
            "education": [],
        }

    provider = get_document_ai_provider(db)
    try:
        return _sanitize_candidate_profile(provider.extract_candidate_profile_from_texts(cleaned))
    except Exception:
        return _sanitize_candidate_profile(heuristic_extract_candidate_profile(cleaned))


def heuristic_parse_job_requirement_profile(title: str, description: str, *, location: str | None = None, work_mode: str | None = None) -> dict[str, Any]:
    haystack = f"{title}\n{description}"
    lowered = haystack.lower()
    role_signals = _infer_role_signals(haystack)
    role_family = role_signals[0] if role_signals else None
    required_skills = _dedupe([match.upper() if match.isupper() else match.title() for match in COMMON_SKILLS_PATTERN.findall(haystack)])[:16]
    certifications = _dedupe([match.upper() if match.isupper() else match for match in COMMON_CERT_PATTERN.findall(haystack)])[:8]

    preferred_patterns = [
        r"(?:nice to have|preferred|bonus|preferred qualifications?)[:\s]+([^\n]+)",
        r"(?:desirable|good to have)[:\s]+([^\n]+)",
    ]
    preferred_skills: list[str] = []
    for pattern in preferred_patterns:
        for line in re.findall(pattern, haystack, re.I):
            for token in re.split(r"[,|/]", line):
                cleaned = re.sub(r"\s+", " ", token).strip(" -")
                if cleaned:
                    preferred_skills.append(cleaned)
    preferred_skills = _dedupe(preferred_skills)[:10]

    seniority = None
    for needle, value in [("principal", "principal"), ("staff", "staff"), ("lead", "lead"), ("senior", "senior"), ("mid", "mid"), ("junior", "junior"), ("graduate", "graduate")]:
        if needle in lowered:
            seniority = value
            break

    effective_work_mode = work_mode
    if not effective_work_mode:
        if "hybrid" in lowered:
            effective_work_mode = "hybrid"
        elif "remote" in lowered:
            effective_work_mode = "remote"
        elif any(token in lowered for token in ("on-site", "onsite", "office-based")):
            effective_work_mode = "onsite"

    risk_flags: list[str] = []
    risk_mapping = {
        "citizenship": "citizenship_required",
        "permanent resident": "residency_required",
        "security clearance": "security_clearance",
        "driver license": "driver_license",
        "on-call": "on_call",
        "weekend": "weekend_work",
        "shift": "shift_work",
    }
    for needle, tag in risk_mapping.items():
        if needle in lowered:
            risk_flags.append(tag)

    location_signals = _dedupe([item for item in [location, effective_work_mode] if str(item or "").strip()])
    return {
        "role_family": role_family,
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "certifications": certifications,
        "location_signals": location_signals,
        "work_mode": effective_work_mode,
        "seniority": seniority,
        "risk_flags": _dedupe(risk_flags),
    }


def parse_job_requirement_profile(title: str, description: str, *, location: str | None = None, work_mode: str | None = None, db: Session | None = None) -> dict[str, Any]:
    fallback = heuristic_parse_job_requirement_profile(title, description, location=location, work_mode=work_mode)
    content = re.sub(r"\s+", " ", f"{title}\n{description}").strip()
    if not content:
        return fallback

    provider = get_llm_provider(db)
    if isinstance(provider, NullLLMProvider):
        return fallback

    try:
        parsed = provider.generate_json(
            model=get_settings().openai_review_model,
            instructions=(
                "Extract a structured job requirement profile from this job title and description. "
                "Keep the result factual, compact, and grounded to the input only. "
                "Use role families such as DevOps, Cloud, Security, Infrastructure, Networking, or IT Support when supported."
            ),
            payload={
                "title": title,
                "description": description[:14000],
                "location": location,
                "work_mode": work_mode,
            },
            schema=JOB_REQUIREMENT_SCHEMA,
        )
    except Exception:
        return fallback

    result = {
        "role_family": parsed.get("role_family") or fallback["role_family"],
        "required_skills": _dedupe([*(parsed.get("required_skills") or []), *fallback["required_skills"]])[:16],
        "preferred_skills": _dedupe(list(parsed.get("preferred_skills") or []))[:10],
        "certifications": _dedupe([*(parsed.get("certifications") or []), *fallback["certifications"]])[:8],
        "location_signals": _dedupe([*(parsed.get("location_signals") or []), *fallback["location_signals"]])[:6],
        "work_mode": parsed.get("work_mode") or fallback["work_mode"],
        "seniority": parsed.get("seniority") or fallback["seniority"],
        "risk_flags": _dedupe([*(parsed.get("risk_flags") or []), *fallback["risk_flags"]])[:10],
    }
    return result


def _infer_role_signals(text: str) -> list[str]:
    lowered = text.lower()
    mapping = {
        "Cloud": ["aws", "azure", "gcp", "cloud"],
        "DevOps": ["devops", "terraform", "ci/cd", "pipeline", "kubernetes", "docker"],
        "Infrastructure": ["infrastructure", "linux", "windows server", "vmware", "support"],
        "Networking": ["network", "routing", "switching", "ccna"],
        "Security": ["security", "soc", "siem", "iam"],
        "IT Support": ["service desk", "desktop", "support", "l1", "l2"],
    }
    return [role for role, needles in mapping.items() if any(needle in lowered for needle in needles)]


def _split_paragraphs(text: str, *, limit: int = 6) -> list[str]:
    paragraphs = [re.sub(r"\s+", " ", block).strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    return [paragraph for paragraph in paragraphs if paragraph][:limit]


def _prompt_logic_lines(text: str, *, limit: int = 10) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip(" -\t") for line in text.splitlines() if line.strip()]
    picked: list[str] = []
    for line in lines:
        if len(line.split()) < 3:
            continue
        picked.append(line)
        if len(picked) >= limit:
            break
    return picked


def extract_document_library_payload(
    text: str,
    *,
    document_kind: str,
    file_name: str | None = None,
    file_path: str | Path | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    normalized = normalize_document_text(text, file_name=file_name, file_path=file_path, db=db)
    profile = extract_candidate_profile_from_texts([normalized], db=db)
    display_title = Path(file_name or "document").stem.replace("_", " ").replace("-", " ").strip().title() or "Document"
    role_signals = _dedupe([*(_infer_role_signals(normalized)), *(profile.get("skills") or [])[:8]])[:12]
    identity = {
        "full_name": profile.get("full_name"),
        "email": profile.get("email"),
        "phone": profile.get("phone"),
        "location": profile.get("location"),
        "website": profile.get("website"),
    }
    paragraphs = _split_paragraphs(normalized)
    cover_body = paragraphs if document_kind == "cover_letter" else []
    prompt_logic = _prompt_logic_lines(normalized) if document_kind == "prompt" else []
    summary = profile.get("summary")
    if document_kind == "cover_letter" and not summary:
        summary = paragraphs[0] if paragraphs else None
    if document_kind == "prompt" and not summary:
        summary = prompt_logic[0] if prompt_logic else None
    return {
        "document_kind": document_kind,
        "title": display_title,
        "normalized_text": normalized,
        "identity": identity,
        "summary": summary,
        "technical_skills": _dedupe(list(profile.get("technical_skills") or profile.get("skills") or []))[:18],
        "skills": _dedupe(list(profile.get("technical_skills") or profile.get("skills") or []))[:18],
        "certifications": _dedupe(list(profile.get("certifications") or []))[:10],
        "experience": list(profile.get("experience") or [])[:8],
        "projects": list(profile.get("projects") or [])[:6],
        "education": _dedupe(list(profile.get("education") or []))[:8],
        "cover_letter_body": cover_body,
        "prompt_logic": prompt_logic,
        "role_signals": role_signals,
    }


def get_llm_provider(db: Session | None = None) -> LLMProvider:
    runtime = resolve_openai_generation_runtime(db)
    if runtime and runtime.api_key:
        return OpenAIResponsesProvider(api_key=runtime.api_key, base_url=runtime.base_url)
    return NullLLMProvider()
