from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None


class ResumeRenderService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def render(self, *, artifact_dir: Path, html: str, file_stem: str = "resume_preview") -> tuple[Path, Path | None, dict[str, Any]]:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        html_path = artifact_dir / f"{file_stem}.html"
        pdf_path = artifact_dir / f"{file_stem}.pdf"
        html_path.write_text(html, encoding="utf-8")
        metrics = {"engine": "html-only", "estimated_pages": 1, "html_path": str(html_path)}
        rendered, measured = self._render_with_puppeteer(html_path, pdf_path)
        if measured.get("error"):
            metrics["puppeteer_error"] = measured["error"]
        if rendered:
            metrics.update({"engine": "puppeteer", "pdf_path": str(pdf_path), **measured})
            return html_path, pdf_path, metrics
        rendered, measured = self._render_with_playwright(html_path, pdf_path)
        if measured.get("error"):
            metrics["playwright_error"] = measured["error"]
        if rendered:
            metrics.update({"engine": "playwright", "pdf_path": str(pdf_path), **measured})
            return html_path, pdf_path, metrics
        return html_path, None, metrics

    def smoke_test(self, *, artifact_dir: Path) -> dict[str, Any]:
        html = """<!doctype html><html><head><meta charset='utf-8'><style>@page { size:A4; margin:10mm; } body { margin:0; font-family:Arial,sans-serif; } .sheet { width:210mm; min-height:277mm; padding:10mm; box-sizing:border-box; } h1 { font-size:20px; margin:0 0 8px; }</style></head><body><main class='sheet'><h1>Document Worker Smoke Test</h1><p>Renderer bootstrap validation.</p></main></body></html>"""
        html_path, pdf_path, metrics = self.render(artifact_dir=artifact_dir, html=html, file_stem="document_worker_smoke")
        return {
            "ready": bool(pdf_path and pdf_path.exists()),
            "html_path": str(html_path),
            "pdf_path": str(pdf_path) if pdf_path else None,
            "metrics": metrics,
        }

    def _render_with_puppeteer(self, html_path: Path, pdf_path: Path) -> tuple[bool, dict[str, Any]]:
        script_path = Path(self.settings.renderer_script_path).resolve()
        package_dir = Path(self.settings.renderer_package_dir).resolve()
        node_bin = shutil.which(self.settings.renderer_node_bin) or self.settings.renderer_node_bin
        if not script_path.exists() or shutil.which(node_bin) is None:
            return False, {}
        try:
            completed = subprocess.run(
                [node_bin, str(script_path), str(html_path.resolve()), str(pdf_path.resolve())],
                cwd=str(package_dir),
                check=True,
                timeout=self.settings.renderer_timeout_seconds,
                capture_output=True,
                text=True,
                env={
                    **__import__("os").environ,
                    **({"PUPPETEER_EXECUTABLE_PATH": self.settings.puppeteer_executable_path} if self.settings.puppeteer_executable_path else {}),
                },
            )
            metrics = self._parse_metrics(completed.stdout)
            if not metrics:
                error_text = (completed.stderr or completed.stdout or "").strip()
                return False, {"error": error_text[-4000:]}
        except Exception as exc:
            return False, {"error": f"{type(exc).__name__}: {exc}"}
        return pdf_path.exists(), metrics

    def _render_with_playwright(self, html_path: Path, pdf_path: Path) -> tuple[bool, dict[str, Any]]:
        if sync_playwright is None:
            return False, {}
        try:
            import asyncio
            asyncio.get_running_loop()
            return False, {"error": "Playwright sync fallback is disabled inside the running asyncio worker process"}
        except RuntimeError:
            pass
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    executable_path=self.settings.puppeteer_executable_path or None,
                )
                page = browser.new_page(viewport={"width": 1240, "height": 1754})
                page.goto(html_path.resolve().as_uri(), wait_until="load")
                page.pdf(path=str(pdf_path), format="A4", print_background=True, prefer_css_page_size=True)
                metrics = page.evaluate(
                    """() => {
                        const mmToPx = (mm) => (mm / 25.4) * 96;
                        const sheet = document.querySelector('.sheet') || document.body;
                        const rect = sheet.getBoundingClientRect();
                        const pageHeightPx = mmToPx(297);
                        const printableHeightPx = mmToPx(277);
                        const contentHeight = Math.max(sheet.scrollHeight, rect.height);
                        return {
                            estimated_pages: Math.max(1, Math.ceil(contentHeight / pageHeightPx)),
                            content_height_px: Math.round(contentHeight),
                            printable_height_px: Math.round(printableHeightPx),
                            overflow_px: Math.max(0, Math.round(contentHeight - printableHeightPx)),
                            white_space_ratio: Number((contentHeight > 0 ? Math.max(0, 1 - (rect.height / contentHeight)) : 0).toFixed(4)),
                        };
                    }"""
                )
                browser.close()
            return pdf_path.exists(), metrics
        except Exception as exc:
            return False, {"error": f"{type(exc).__name__}: {exc}"}

    def _parse_metrics(self, stdout: str) -> dict[str, Any]:
        text = str(stdout or "").strip().splitlines()
        if not text:
            return {}
        for line in reversed(text):
            candidate = line.strip()
            if not candidate.startswith("{"):
                continue
            try:
                payload = json.loads(candidate)
                return dict(payload)
            except Exception:
                continue
        return {}
