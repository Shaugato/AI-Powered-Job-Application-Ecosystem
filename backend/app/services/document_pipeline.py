from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.services.document_ensemble import DocumentEnsembleService
from backend.app.services.llm import extract_document_library_payload, get_llm_provider

try:
    from docling.document_converter import DocumentConverter
except Exception:  # pragma: no cover
    DocumentConverter = None

try:
    import fitz
except Exception:  # pragma: no cover
    fitz = None

try:
    import pdfplumber
except Exception:  # pragma: no cover
    pdfplumber = None

LAYOUT_REPAIR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "section": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["section", "confidence", "evidence"],
            },
        },
        "ambiguity_flags": {"type": "array", "items": {"type": "string"}},
        "repair_hints": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["sections", "ambiguity_flags", "repair_hints"],
}

SECTION_LABELS = {
    "identity": {"contact", "identity", "personal information"},
    "summary": {"summary", "profile", "professional summary"},
    "technical_skills": {"technical skills", "skills", "core skills"},
    "experience": {"experience", "work experience", "employment history", "professional experience"},
    "projects": {"projects", "project experience"},
    "certifications": {"certifications", "licenses"},
    "education": {"education"},
}


@dataclass
class DocumentPipelineResult:
    normalized_text: str
    payload: dict[str, Any]
    layout_blueprint: dict[str, Any]
    parser_confidence: float
    ambiguity_flags: list[str]
    validation_result: dict[str, Any]
    repair_hints: list[dict[str, Any]]
    source_metadata: dict[str, Any]
    stage_records: list[dict[str, Any]]
    review_summary: str | None = None


class DocumentPipelineService:
    def __init__(self, db: Session | None) -> None:
        self.db = db
        self.settings = get_settings()
        self.llm = get_llm_provider(db)
        self.ensemble = DocumentEnsembleService()

    def process_file(self, file_path: Path, *, document_kind: str, role_hints: list[str] | None = None) -> DocumentPipelineResult:
        role_hints = role_hints or []
        stage_records: list[dict[str, Any]] = []
        source_metadata = self._file_intake(file_path)
        stage_records.append(self._stage("file_intake", 0, "completed", source_metadata, confidence=1.0))

        docling_result = self._docling_convert(file_path)
        stage_records.append(self._stage("docling_conversion", 1, docling_result["status"], docling_result, confidence=docling_result["confidence"], repair_hints=docling_result.get("repair_hints") or []))

        rendering = self._render_pages_and_spans(file_path, docling_result)
        stage_records.append(self._stage("page_rendering", 2, rendering["status"], rendering, confidence=rendering["confidence"]))

        layout_blueprint = self._layout_blueprint(file_path, docling_result["text"], rendering)
        stage_records.append(self._stage("layout_zoning", 3, "completed", layout_blueprint, confidence=layout_blueprint["confidence"], ambiguity_flags=layout_blueprint.get("ambiguity_flags") or []))

        adjudicated_layout = self._adjudicate_layout_if_needed(docling_result["text"], layout_blueprint)
        if adjudicated_layout is not layout_blueprint:
            layout_blueprint = adjudicated_layout
            stage_records.append(self._stage("layout_zoning", 4, "repaired", layout_blueprint, confidence=layout_blueprint["confidence"], ambiguity_flags=layout_blueprint.get("ambiguity_flags") or [], repair_hints=layout_blueprint.get("repair_hints") or []))

        payload = extract_document_library_payload(docling_result["text"], document_kind=document_kind, file_name=file_path.name, file_path=file_path, db=self.db)
        payload["layout_blueprint"] = layout_blueprint
        payload["section_metadata"] = self._section_metadata(payload, docling_result["text"], rendering.get("text_spans") or [])
        payload["source_metadata"] = source_metadata | {
            "page_count": rendering.get("page_count"),
            "page_images": rendering.get("page_images") or [],
            "text_spans": rendering.get("text_spans") or [],
            "reading_order": rendering.get("reading_order") or [],
            "runtime": self.ensemble.runtime_capabilities(),
            "ocr_status": rendering.get("ocr_status") or {},
            "role_hints": role_hints,
        }
        payload["parser_confidence"] = round((docling_result["confidence"] + layout_blueprint["confidence"] + rendering["confidence"]) / 3.0, 4)
        payload["ambiguity_flags"] = list(layout_blueprint.get("ambiguity_flags") or [])
        validation_result = self._validate_payload(payload)
        repair_hints = self._repair_hints(payload, validation_result, layout_blueprint)
        stage_records.append(self._stage("structured_extraction", 5, "completed" if validation_result["valid"] else "needs_review", {"section_counts": validation_result["section_counts"]}, confidence=payload["parser_confidence"], validation_result=validation_result, repair_hints=repair_hints, ambiguity_flags=payload["ambiguity_flags"]))

        review_summary = None
        if payload["parser_confidence"] < self.settings.document_review_threshold or payload["ambiguity_flags"] or not validation_result["valid"]:
            review_summary = "Document extraction requires review because confidence or layout validation fell below the configured threshold."

        return DocumentPipelineResult(
            normalized_text=docling_result["text"],
            payload=payload,
            layout_blueprint=layout_blueprint,
            parser_confidence=payload["parser_confidence"],
            ambiguity_flags=payload["ambiguity_flags"],
            validation_result=validation_result,
            repair_hints=repair_hints,
            source_metadata=payload["source_metadata"],
            stage_records=stage_records,
            review_summary=review_summary,
        )

    def _file_intake(self, file_path: Path) -> dict[str, Any]:
        mime_type, _ = mimetypes.guess_type(str(file_path))
        return {
            "file_name": file_path.name,
            "file_size_bytes": file_path.stat().st_size,
            "mime_type": mime_type or "application/octet-stream",
            "extension": file_path.suffix.lower(),
            "content_hash": hashlib.sha256(file_path.read_bytes()).hexdigest(),
        }

    def _docling_convert(self, file_path: Path) -> dict[str, Any]:
        if DocumentConverter is not None:
            try:
                converter = DocumentConverter()
                result = converter.convert(str(file_path))
                document = getattr(result, "document", None)
                text = ""
                if document is not None and hasattr(document, "export_to_markdown"):
                    text = document.export_to_markdown()
                elif hasattr(result, "document") and hasattr(result.document, "export_to_text"):
                    text = result.document.export_to_text()
                if text:
                    return {"status": "completed", "engine": "docling", "text": self._normalize_text(text), "confidence": 0.92, "repair_hints": []}
            except Exception as exc:
                fallback = self._fallback_extract(file_path)
                fallback["status"] = "fallback"
                fallback["engine"] = "fallback"
                fallback["repair_hints"] = [{"action": "docling_failed", "detail": f"{type(exc).__name__}: {exc}"}]
                return fallback
        fallback = self._fallback_extract(file_path)
        fallback["status"] = "fallback"
        fallback["engine"] = "fallback"
        fallback["repair_hints"] = [{"action": "docling_unavailable"}]
        return fallback

    def _fallback_extract(self, file_path: Path) -> dict[str, Any]:
        suffix = file_path.suffix.lower()
        text = ""
        if suffix in {".txt", ".md", ".tex"}:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        elif suffix == ".docx":
            try:
                from docx import Document

                document = Document(file_path)
                text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            except Exception:
                text = ""
        elif suffix == ".pdf":
            if fitz is not None:
                try:
                    document = fitz.open(str(file_path))
                    text = "\n".join(page.get_text("text") for page in document)
                except Exception:
                    text = ""
            if not text:
                try:
                    from pypdf import PdfReader

                    reader = PdfReader(str(file_path))
                    text = "\n".join(page.extract_text() or "" for page in reader.pages)
                except Exception:
                    text = ""
        return {"text": self._normalize_text(text), "confidence": 0.66 if text else 0.0, "repair_hints": []}

    def _render_pages_and_spans(self, file_path: Path, docling_result: dict[str, Any]) -> dict[str, Any]:
        page_images: list[str] = []
        text_spans: list[dict[str, Any]] = []
        reading_order: list[dict[str, Any]] = []
        page_count = 1
        cache_root = self.settings.library_dir / "_page_cache" / file_path.stem
        if cache_root.exists():
            shutil.rmtree(cache_root, ignore_errors=True)
        cache_root.mkdir(parents=True, exist_ok=True)
        if file_path.suffix.lower() == ".pdf" and fitz is not None:
            try:
                document = fitz.open(str(file_path))
                page_count = len(document)
                for index, page in enumerate(document, start=1):
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
                    image_path = cache_root / f"page-{index:03d}.png"
                    pix.save(str(image_path))
                    page_images.append(str(image_path))
                    reading_order.append({"page": index, "line_order": index})
                if pdfplumber is not None:
                    with pdfplumber.open(str(file_path)) as pdf:
                        for page_index, page in enumerate(pdf.pages, start=1):
                            for word in page.extract_words() or []:
                                text_spans.append({"page": page_index, "text": word.get("text"), "bbox": [word.get("x0"), word.get("top"), word.get("x1"), word.get("bottom")], "confidence": 0.9, "engine": "pdfplumber"})
            except Exception:
                pass
        ocr_spans, ocr_status, ocr_confidence = self.ensemble.extract_text_spans(page_images)
        if ocr_spans:
            text_spans = self._merge_spans(text_spans, ocr_spans)
        if not text_spans:
            lines = [line.strip() for line in str(docling_result.get("text") or "").splitlines() if line.strip()]
            for index, line in enumerate(lines[:600], start=1):
                text_spans.append({"page": 1, "text": line, "bbox": [0, index * 12, 800, index * 12 + 10], "confidence": 0.55, "engine": "heuristic"})
                reading_order.append({"page": 1, "line_order": index})
        if not reading_order:
            reading_order = [{"page": span.get("page", 1), "line_order": index} for index, span in enumerate(text_spans, start=1)]
        confidence = max(0.45, min(0.92, 0.68 + (0.12 if ocr_spans else 0.0) + (0.08 if page_images else 0.0)))
        return {
            "status": "completed",
            "page_count": page_count,
            "page_images": page_images,
            "text_spans": text_spans,
            "reading_order": reading_order,
            "ocr_status": ocr_status,
            "confidence": round((confidence + ocr_confidence) / 2.0, 4) if ocr_confidence else round(confidence, 4),
        }

    def _layout_blueprint(self, file_path: Path, normalized_text: str, rendering: dict[str, Any]) -> dict[str, Any]:
        lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
        detected_sections: list[dict[str, Any]] = []
        current = None
        for index, line in enumerate(lines, start=1):
            normalized = re.sub(r"[^a-z ]", "", line.lower()).strip()
            matched = next((label for label, needles in SECTION_LABELS.items() if normalized in needles), None)
            if matched:
                current = {"section": matched, "reading_order": len(detected_sections) + 1, "start_line": index, "evidence": [line], "bbox": [0, index * 12, 800, index * 12 + 10], "confidence": 0.82}
                detected_sections.append(current)
                continue
            if current and len(current["evidence"]) < 4:
                current["evidence"].append(line)

        ensemble_layout = self.ensemble.detect_layout(
            image_paths=list(rendering.get("page_images") or []),
            text_spans=list(rendering.get("text_spans") or []),
            raw_lines=lines,
        )
        ambiguity_flags: list[str] = list(ensemble_layout.get("ambiguity_flags") or [])
        present = {item["section"] for item in detected_sections}
        for required in ("experience", "technical_skills", "education"):
            if required not in present and file_path.suffix.lower() in {".pdf", ".docx"}:
                ambiguity_flags.append(f"missing_{required}_section")

        confidence = min(0.96, 0.58 + (0.16 if detected_sections else 0.0) + float(ensemble_layout.get("confidence") or 0.0) * 0.25)
        return {
            "detected_sections": detected_sections,
            "bounding_boxes": [{"section": item["section"], "bbox": item["bbox"]} for item in detected_sections],
            "reading_order": rendering.get("reading_order") or [],
            "raw_line_estimates": {item["section"]: len(item["evidence"]) for item in detected_sections},
            "section_confidence": {item["section"]: item["confidence"] for item in detected_sections},
            "ambiguity_flags": list(dict.fromkeys(ambiguity_flags)),
            "engines": {**(rendering.get("ocr_status") or {}), **dict(ensemble_layout.get("engine_status") or {})},
            "regions": list(ensemble_layout.get("regions") or []),
            "semantic_scores": list(ensemble_layout.get("semantic_scores") or []),
            "confidence": round(confidence, 4),
        }

    def _adjudicate_layout_if_needed(self, normalized_text: str, layout_blueprint: dict[str, Any]) -> dict[str, Any]:
        if not layout_blueprint.get("ambiguity_flags"):
            return layout_blueprint
        try:
            payload = self.llm.generate_json(
                model=self.settings.openai_multimodal_model,
                instructions="Resolve section ambiguity for a resume or cover letter layout. Use only the supplied text and current layout guesses. Return the most likely section labels with evidence and repair hints. Do not invent unsupported sections.",
                payload={"text": normalized_text[:12000], "layout_blueprint": layout_blueprint},
                schema=LAYOUT_REPAIR_SCHEMA,
            )
        except Exception:
            return layout_blueprint
        repaired = dict(layout_blueprint)
        repaired["detected_sections"] = [
            {"section": item["section"], "reading_order": index, "start_line": index, "evidence": list(item.get("evidence") or []), "bbox": [0, index * 12, 800, index * 12 + 10], "confidence": float(item.get("confidence") or 0.6)}
            for index, item in enumerate(payload.get("sections") or [], start=1)
        ] or repaired["detected_sections"]
        repaired["ambiguity_flags"] = list(payload.get("ambiguity_flags") or [])
        repaired["confidence"] = max(float(repaired.get("confidence") or 0.0), 0.76)
        repaired["repair_hints"] = [{"action": "llm_adjudication", "detail": hint} for hint in (payload.get("repair_hints") or [])]
        return repaired

    def _section_metadata(self, payload: dict[str, Any], normalized_text: str, text_spans: list[dict[str, Any]]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        identity = payload.get("identity") or {}
        if identity:
            metadata["identity"] = {
                "value": identity,
                "confidence": self._mean_confidence(identity.values(), normalized_text),
                "evidence_spans": [self._span_for_value(value, normalized_text, text_spans) for value in identity.values() if str(value or "").strip()],
                "provenance": [{"source": "structured_extraction", "engine": "openai"}],
            }
        if payload.get("summary"):
            metadata["summary"] = {
                "value": payload.get("summary"),
                "confidence": self._confidence_for_value(str(payload.get("summary") or ""), normalized_text),
                "evidence_spans": [self._span_for_value(str(payload.get("summary") or ""), normalized_text, text_spans)],
                "provenance": [{"source": "structured_extraction", "engine": "openai"}],
            }
        metadata["technical_skills"] = [self._value_metadata(value, normalized_text, text_spans, taxonomy="skill") for value in (payload.get("technical_skills") or payload.get("skills") or [])]
        metadata["certifications"] = [self._value_metadata(value, normalized_text, text_spans, taxonomy="certification") for value in (payload.get("certifications") or [])]
        metadata["education"] = [self._value_metadata(value, normalized_text, text_spans, taxonomy="education") for value in (payload.get("education") or [])]
        metadata["experience"] = [self._entry_metadata(entry, normalized_text, text_spans, taxonomy="experience") for entry in (payload.get("experience") or [])]
        metadata["projects"] = [self._entry_metadata(entry, normalized_text, text_spans, taxonomy="project") for entry in (payload.get("projects") or [])]
        metadata["cover_letter_body"] = [self._value_metadata(value, normalized_text, text_spans, taxonomy="cover_letter_body") for value in (payload.get("cover_letter_body") or [])]
        metadata["prompt_logic"] = [self._value_metadata(value, normalized_text, text_spans, taxonomy="prompt_logic") for value in (payload.get("prompt_logic") or [])]
        return metadata

    def _entry_metadata(self, entry: dict[str, Any], normalized_text: str, text_spans: list[dict[str, Any]], *, taxonomy: str) -> dict[str, Any]:
        title = str(entry.get("title") or "").strip()
        subtitle = str(entry.get("subtitle") or "").strip() or None
        bullets = [str(item).strip() for item in (entry.get("bullets") or []) if str(item).strip()]
        all_values = [title, subtitle or "", *bullets]
        return {
            "value": {"title": title, "subtitle": subtitle, "bullets": bullets},
            "confidence": self._mean_confidence(all_values, normalized_text),
            "evidence_spans": [self._span_for_value(value, normalized_text, text_spans) for value in all_values if value],
            "taxonomy": taxonomy,
            "provenance": [{"source": "structured_extraction", "engine": "openai"}],
        }

    def _value_metadata(self, value: Any, normalized_text: str, text_spans: list[dict[str, Any]], *, taxonomy: str) -> dict[str, Any]:
        text = str(value or "").strip()
        return {
            "value": text,
            "confidence": self._confidence_for_value(text, normalized_text),
            "evidence_spans": [self._span_for_value(text, normalized_text, text_spans)] if text else [],
            "taxonomy": taxonomy,
            "provenance": [{"source": "structured_extraction", "engine": "openai"}],
        }

    def _validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        section_counts = {
            "technical_skills": len(payload.get("technical_skills") or []),
            "experience": len(payload.get("experience") or []),
            "projects": len(payload.get("projects") or []),
            "certifications": len(payload.get("certifications") or []),
            "education": len(payload.get("education") or []),
        }
        valid = any(section_counts.values()) and bool(payload.get("normalized_text"))
        warnings: list[str] = []
        if not payload.get("identity", {}).get("full_name"):
            warnings.append("identity_missing")
        if section_counts["experience"] == 0 and payload.get("document_kind") == "resume":
            warnings.append("experience_missing")
        return {"valid": valid, "warnings": warnings, "section_counts": section_counts}

    def _repair_hints(self, payload: dict[str, Any], validation_result: dict[str, Any], layout_blueprint: dict[str, Any]) -> list[dict[str, Any]]:
        hints: list[dict[str, Any]] = []
        for warning in validation_result.get("warnings") or []:
            if warning == "identity_missing":
                hints.append({"action": "request_identity_review", "detail": "Identity fields were not extracted with confidence."})
            if warning == "experience_missing":
                hints.append({"action": "review_experience_section", "detail": "No experience section was extracted from a resume asset."})
        for flag in layout_blueprint.get("ambiguity_flags") or []:
            hints.append({"action": "review_layout_ambiguity", "detail": flag})
        return hints

    def _stage(self, stage_name: str, stage_index: int, status: str, payload: dict[str, Any], *, confidence: float = 0.0, validation_result: dict[str, Any] | None = None, repair_hints: list[dict[str, Any]] | None = None, ambiguity_flags: list[str] | None = None) -> dict[str, Any]:
        return {
            "stage_name": stage_name,
            "stage_index": stage_index,
            "status": status,
            "payload": payload,
            "confidence": float(confidence or 0.0),
            "provenance": [{"engine": payload.get("engine")}] if payload.get("engine") else [],
            "validation_result": validation_result or {},
            "repair_hints": repair_hints or [],
            "ambiguity_flags": ambiguity_flags or [],
        }

    def _span_for_value(self, value: str, normalized_text: str, text_spans: list[dict[str, Any]]) -> dict[str, Any]:
        text = str(value or "").strip()
        if not text:
            return {"start": None, "end": None, "confidence": 0.0}
        haystack = normalized_text.lower()
        needle = text.lower()
        start = haystack.find(needle)
        if start < 0:
            compact = re.sub(r"\s+", " ", needle)
            start = re.sub(r"\s+", " ", haystack).find(compact)
            if start < 0:
                for span in text_spans:
                    if compact and compact in re.sub(r"\s+", " ", str(span.get("text") or "").lower()):
                        bbox = list(span.get("bbox") or [None, None, None, None])
                        return {"start": None, "end": None, "confidence": float(span.get("confidence") or 0.55), "page": span.get("page"), "bbox": bbox}
                return {"start": None, "end": None, "confidence": 0.45}
        return {"start": start, "end": start + len(text), "confidence": 0.9}

    def _confidence_for_value(self, value: str, normalized_text: str) -> float:
        span = self._span_for_value(value, normalized_text, [])
        return float(span.get("confidence") or 0.0)

    def _mean_confidence(self, values: Any, normalized_text: str) -> float:
        scores = [self._confidence_for_value(str(value), normalized_text) for value in values if str(value or "").strip()]
        return round(sum(scores) / max(len(scores), 1), 4) if scores else 0.0

    def _normalize_text(self, text: str) -> str:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ 	]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    def _merge_spans(self, base: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[int, str]] = set()
        merged: list[dict[str, Any]] = []
        for item in [*base, *extra]:
            key = (int(item.get("page") or 1), str(item.get("text") or "").strip().casefold())
            if not key[1] or key in seen:
                continue
            seen.add(key)
            merged.append(item)
        merged.sort(key=lambda item: (int(item.get("page") or 1), float((item.get("bbox") or [0, 0, 0, 0])[1] or 0), float((item.get("bbox") or [0, 0, 0, 0])[0] or 0)))
        return merged
