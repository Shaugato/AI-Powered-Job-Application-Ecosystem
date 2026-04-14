from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.connectors.base import SourceConnector
from backend.app.core.config import get_settings

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    PlaywrightTimeoutError = Exception
    sync_playwright = None


class CompanyPortalConnector(SourceConnector):
    def __init__(self) -> None:
        super().__init__(
            source_name="company_portal",
            auto_submit_certified=True,
            notes=[
                "Certified for low-friction adapters with deterministic field maps.",
                "Escalate to review when essays or declarations are detected.",
            ],
        )
        self.settings = get_settings()

    def build_search_url(self, *, query: str, location: str | None = None, remote_policy: str | None = None, metadata: dict | None = None) -> str | None:
        metadata = metadata or {}
        return str(metadata.get("search_url") or metadata.get("base_url") or "").strip() or None

    def submit_application(self, field_map: dict[str, Any]) -> dict[str, object]:
        target_url = str(field_map.get("target_url") or "").strip()
        resume_path = Path(str(field_map.get("resume_path") or "")).expanduser()
        cover_path = Path(str(field_map.get("cover_letter_path") or "")).expanduser() if field_map.get("cover_letter_path") else None
        allow_auto_submit = bool(field_map.get("allow_auto_submit"))
        storage_state_path = str(field_map.get("storage_state_path") or "").strip()
        login_url = str(field_map.get("login_url") or "").strip()

        log: list[dict[str, str]] = []
        execution_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        execution_dir = self.settings.browser_run_dir / execution_id
        execution_dir.mkdir(parents=True, exist_ok=True)

        if not target_url:
            return self._result("failed", log, "Missing target URL", execution_dir)
        if not resume_path.exists():
            return self._result("failed", log, f"Missing resume artifact: {resume_path}", execution_dir)
        if sync_playwright is None:
            return self._result("review_required", log, "Playwright is not installed in the runtime", execution_dir)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.settings.playwright_headless)
                context_kwargs: dict[str, Any] = {}
                if storage_state_path and Path(storage_state_path).exists():
                    context_kwargs["storage_state"] = storage_state_path
                    log.append(self._entry("Loaded stored browser session for this connection"))
                context = browser.new_context(**context_kwargs)
                page = context.new_page()
                log.append(self._entry(f"Navigating to {target_url}"))
                page.goto(target_url, wait_until="domcontentloaded", timeout=self.settings.playwright_timeout_ms)
                page.screenshot(path=str(execution_dir / "arrival.png"), full_page=True)

                if self._looks_like_login(page):
                    if login_url and not context_kwargs.get("storage_state"):
                        context.close()
                        browser.close()
                        return self._result("review_required", log, f"Authentication gate detected. Connect and upload a browser session for {login_url}", execution_dir)
                    context.close()
                    browser.close()
                    return self._result("review_required", log, "Authentication gate detected on the application portal", execution_dir)

                self._fill_standard_fields(page, field_map, log)
                self._upload_documents(page, resume_path, cover_path, log)
                page.screenshot(path=str(execution_dir / "filled.png"), full_page=True)

                if self._needs_review(page):
                    context.close()
                    browser.close()
                    return self._result("review_required", log, "Complex form elements detected; pausing for review", execution_dir)

                if not allow_auto_submit:
                    context.close()
                    browser.close()
                    return self._result("review_required", log, "Auto-submit disabled by plan policy", execution_dir)

                clicked = self._click_submit(page, log)
                if not clicked:
                    context.close()
                    browser.close()
                    return self._result("review_required", log, "No deterministic submit button detected", execution_dir)

                page.wait_for_timeout(1200)
                page.screenshot(path=str(execution_dir / "submitted.png"), full_page=True)
                context.close()
                browser.close()
                return self._result("submitted", log, "Submission action completed", execution_dir)
        except PlaywrightTimeoutError:
            return self._result("failed", log, "Playwright timed out while interacting with the application page", execution_dir)
        except Exception as exc:  # pragma: no cover
            return self._result("failed", log, f"Playwright execution failed: {type(exc).__name__}: {exc}", execution_dir)

    def _fill_standard_fields(self, page, field_map: dict[str, Any], log: list[dict[str, str]]) -> None:
        mappings = [
            ("full_name", ["input[name*='name' i]", "input[placeholder*='name' i]", "input[id*='name' i]", "textarea[name*='name' i]"], "full name"),
            ("email", ["input[type='email']", "input[name*='email' i]", "input[placeholder*='email' i]"], "email"),
            ("phone", ["input[type='tel']", "input[name*='phone' i]", "input[placeholder*='phone' i]"], "phone"),
            ("location", ["input[name*='location' i]", "input[placeholder*='location' i]", "input[name*='city' i]"], "location"),
            ("website", ["input[name*='website' i]", "input[name*='portfolio' i]", "input[name*='linkedin' i]"], "website"),
        ]
        for key, selectors, label in mappings:
            value = str(field_map.get(key) or "").strip()
            if not value:
                continue
            if self._fill_first_available(page, selectors, value):
                log.append(self._entry(f"Filled {label}"))

        cover_text = str(field_map.get("cover_letter_text") or "").strip()
        if cover_text:
            cover_selectors = [
                "textarea[name*='cover' i]",
                "textarea[placeholder*='cover' i]",
                "textarea[name*='message' i]",
                "textarea[name*='letter' i]",
            ]
            if self._fill_first_available(page, cover_selectors, cover_text):
                log.append(self._entry("Filled cover letter text area"))

    def _upload_documents(self, page, resume_path: Path, cover_path: Path | None, log: list[dict[str, str]]) -> None:
        file_inputs = page.locator("input[type='file']")
        count = file_inputs.count()
        if count == 0:
            return

        file_inputs.nth(0).set_input_files(str(resume_path))
        log.append(self._entry(f"Uploaded resume artifact {resume_path.name}"))
        if count > 1 and cover_path and cover_path.exists():
            file_inputs.nth(1).set_input_files(str(cover_path))
            log.append(self._entry(f"Uploaded cover artifact {cover_path.name}"))

    def _fill_first_available(self, page, selectors: list[str], value: str) -> bool:
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            for index in range(locator.count()):
                target = locator.nth(index)
                try:
                    target.fill(value)
                    return True
                except Exception:
                    continue
        return False

    def _needs_review(self, page) -> bool:
        textarea_count = page.locator("textarea").count()
        page_text = page.locator("body").inner_text(timeout=self.settings.playwright_timeout_ms).lower()
        risky_tokens = ["selection criteria", "merit", "why do you want", "legal declaration", "covering letter"]
        return textarea_count > 2 or any(token in page_text for token in risky_tokens)

    def _looks_like_login(self, page) -> bool:
        password_inputs = page.locator("input[type='password']").count()
        if password_inputs > 0:
            return True
        page_text = page.locator("body").inner_text(timeout=self.settings.playwright_timeout_ms).lower()
        return any(token in page_text for token in ["sign in", "log in", "login", "password"])

    def _click_submit(self, page, log: list[dict[str, str]]) -> bool:
        selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit application')",
            "button:has-text('Apply')",
            "button:has-text('Submit')",
        ]
        for selector in selectors:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            try:
                locator.first.click(timeout=self.settings.playwright_timeout_ms)
                log.append(self._entry(f"Clicked submit control via selector {selector}"))
                return True
            except Exception:
                continue
        return False

    def _result(self, status: str, log: list[dict[str, str]], message: str, execution_dir: Path) -> dict[str, object]:
        log.append(self._entry(message))
        screenshots = [str(path) for path in execution_dir.glob("*.png")]
        return {
            "status": status,
            "log": log,
            "artifacts": screenshots,
            "execution_dir": str(execution_dir),
        }

    def _entry(self, message: str) -> dict[str, str]:
        return {"at": datetime.now(timezone.utc).isoformat(), "message": message}
