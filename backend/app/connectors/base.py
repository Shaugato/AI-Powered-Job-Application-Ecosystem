from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin

from backend.app.core.config import get_settings
from backend.app.schemas.jobs import SourceHealth

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None


@dataclass
class SourceConnector:
    source_name: str
    auto_submit_certified: bool = False
    monitoring_enabled: bool = True
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.settings = get_settings()

    def health(self) -> SourceHealth:
        return SourceHealth(
            source=self.source_name,
            auto_submit_certified=self.auto_submit_certified,
            monitoring_enabled=self.monitoring_enabled,
            status="healthy",
            notes=self.notes,
        )

    def submit_application(self, field_map: dict[str, Any]) -> dict[str, object]:
        return {
            "status": "submitted" if self.auto_submit_certified else "review_required",
            "log": [{"at": datetime.now(timezone.utc).isoformat(), "message": f"{self.source_name} adapter executed deterministic submission plan"}],
            "field_map": field_map,
        }

    def build_search_url(
        self,
        *,
        query: str,
        location: str | None = None,
        remote_policy: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        metadata = metadata or {}
        override = str(metadata.get("search_url") or "").strip()
        return override or None

    def discovery_selectors(self) -> dict[str, list[str]]:
        return {
            "cards": ["article", "li", "div[data-job-id]", "div[data-automation]"],
            "title": ["h3", "h2", "a[title]", "a"],
            "company": ["[data-company]", ".company", "[class*=company]"],
            "location": ["[data-location]", ".location", "[class*=location]"],
            "snippet": ["p", "[class*=description]", "[class*=snippet]"],
            "url": ["a[href]"],
        }

    def discover_jobs(
        self,
        *,
        query: str,
        location: str | None = None,
        remote_policy: str | None = None,
        limit: int = 20,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        search_url = self.build_search_url(query=query, location=location, remote_policy=remote_policy, metadata=metadata)
        if not search_url or sync_playwright is None:
            return []
        return self._discover_with_playwright(search_url=search_url, limit=limit, metadata=metadata or {})

    def _discover_with_playwright(self, *, search_url: str, limit: int, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        selectors = self.discovery_selectors()
        jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.settings.playwright_headless)
            context_kwargs: dict[str, Any] = {}
            storage_state_path = str(metadata.get("storage_state_path") or "").strip()
            if storage_state_path and Path(storage_state_path).exists():
                context_kwargs["storage_state"] = storage_state_path
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.goto(search_url, wait_until="domcontentloaded", timeout=self.settings.playwright_timeout_ms)
            page.wait_for_timeout(1500)
            cards = self._first_locator(page, selectors.get("cards", []))
            count = min(cards.count() if cards is not None else 0, max(limit * 4, limit))
            for index in range(count):
                card = cards.nth(index)
                title = self._locator_text(card, selectors.get("title", []))
                href = self._locator_attribute(card, selectors.get("url", []), "href")
                if not title or not href:
                    continue
                absolute_url = urljoin(search_url, href)
                if absolute_url in seen_urls:
                    continue
                seen_urls.add(absolute_url)
                company = self._locator_text(card, selectors.get("company", [])) or self.source_name.title()
                location_text = self._locator_text(card, selectors.get("location", []))
                snippet = self._locator_text(card, selectors.get("snippet", [])) or title
                jobs.append(
                    {
                        "source": self.source_name,
                        "external_id": self._external_id(absolute_url, title, company),
                        "source_url": absolute_url,
                        "company": company.strip(),
                        "title": title.strip(),
                        "location": location_text.strip() if location_text else None,
                        "work_mode": self._infer_work_mode(location_text or snippet),
                        "description_text": snippet.strip(),
                        "classification_labels": [],
                        "eligibility_flags": [],
                        "risk_flags": self._infer_risk_flags(snippet),
                        "metadata_json": {"search_url": search_url, "discovered_at": datetime.now(timezone.utc).isoformat(), **metadata},
                    }
                )
                if len(jobs) >= limit:
                    break
            context.close()
            browser.close()
        return jobs

    def _infer_work_mode(self, text: str | None) -> str | None:
        haystack = (text or "").lower()
        if "remote" in haystack:
            return "remote"
        if "hybrid" in haystack:
            return "hybrid"
        if haystack:
            return "onsite"
        return None

    def _infer_risk_flags(self, text: str) -> list[str]:
        haystack = text.lower()
        risk_flags: list[str] = []
        if any(token in haystack for token in ["selection criteria", "statement of claims", "cover letter required"]):
            risk_flags.append("essay_required")
        if any(token in haystack for token in ["declaration", "citizenship", "clearance"]):
            risk_flags.append("legal_declaration")
        return risk_flags

    def _first_locator(self, root: Any, selectors: list[str]):
        for selector in selectors:
            locator = root.locator(selector)
            try:
                if locator.count() > 0:
                    return locator
            except Exception:
                continue
        return None

    def _locator_text(self, root: Any, selectors: list[str]) -> str | None:
        for selector in selectors:
            locator = root.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                try:
                    text = locator.nth(index).inner_text(timeout=1000).strip()
                except Exception:
                    continue
                if text:
                    return text
        return None

    def _locator_attribute(self, root: Any, selectors: list[str], attribute: str) -> str | None:
        for selector in selectors:
            locator = root.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                try:
                    value = locator.nth(index).get_attribute(attribute, timeout=1000)
                except Exception:
                    continue
                if value:
                    return value
        return None

    def _external_id(self, absolute_url: str, title: str, company: str) -> str:
        basis = f"{self.source_name}|{absolute_url}|{title}|{company}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def query_terms(query: str, location: str | None = None, remote_policy: str | None = None) -> tuple[str, str | None, str | None]:
    return quote_plus(query.strip()), quote_plus(location.strip()) if location else None, remote_policy
