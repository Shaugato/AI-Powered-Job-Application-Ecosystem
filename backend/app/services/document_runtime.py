from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings
from backend.app.services.document_ensemble import DocumentEnsembleService
from backend.app.services.renderer import ResumeRenderService


class DocumentRuntimeBootstrapService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.ensemble = DocumentEnsembleService()
        self.renderer = ResumeRenderService()
        self.report_path = self.settings.artifacts_dir / "document-worker-smoke" / "runtime-bootstrap.json"

    def bootstrap(self) -> dict[str, Any]:
        report = {
            "document_models": self.ensemble.bootstrap_models(),
            "renderer": self.renderer.smoke_test(artifact_dir=self.settings.artifacts_dir / "document-worker-smoke"),
        }
        report["ready"] = bool(report["document_models"].get("ready")) and bool(report["renderer"].get("ready"))
        self._persist_report(report)
        if self.settings.document_fail_fast_on_startup and not report["ready"]:
            raise RuntimeError(f"Document runtime bootstrap failed: {report}")
        return report

    def status(self) -> dict[str, Any]:
        bootstrap_report = self._load_report()
        runtime_capabilities = self.ensemble.runtime_capabilities()
        ready = bool((bootstrap_report.get("ready") if isinstance(bootstrap_report, dict) else False))
        document_models = dict((bootstrap_report or {}).get("document_models") or {}) if isinstance(bootstrap_report, dict) else {}
        engine_reports = dict(document_models.get("engines") or {})
        effective_device = str(document_models.get("device") or runtime_capabilities.get("device") or "cpu")
        effective_gpu_available = bool(document_models.get("gpu_available")) if document_models else bool(runtime_capabilities.get("gpu_available"))
        effective_cuda_visible = bool(document_models.get("cuda_visible")) if document_models else bool(runtime_capabilities.get("cuda_visible"))
        effective_torch_cuda_usable = bool(document_models.get("torch_cuda_usable")) if document_models else bool(runtime_capabilities.get("torch_cuda_usable"))
        effective_gpu_reason = str(document_models.get("gpu_unavailable_reason") or runtime_capabilities.get("gpu_unavailable_reason") or "")
        effective_device_name = str(document_models.get("device_name") or runtime_capabilities.get("device_name") or "")
        effective_device_capability = document_models.get("device_capability") or runtime_capabilities.get("device_capability")
        effective_supported_arches = document_models.get("supported_arches") or runtime_capabilities.get("supported_arches") or []
        merged_capabilities = {
            "runtime_mode": str(runtime_capabilities.get("runtime_mode") or self.settings.document_runtime_mode),
            "gpu_preferred": bool(runtime_capabilities.get("gpu_preferred")),
            "gpu_available": effective_gpu_available,
            "cuda_visible": effective_cuda_visible,
            "torch_cuda_usable": effective_torch_cuda_usable,
            "gpu_unavailable_reason": effective_gpu_reason or None,
            "device": effective_device,
            "device_name": effective_device_name or None,
            "device_capability": effective_device_capability,
            "supported_arches": list(effective_supported_arches),
            "layoutlmv3": str((engine_reports.get("layoutlmv3") or {}).get("status") or runtime_capabilities.get("layoutlmv3") or "unknown"),
            "doclayout_yolo": str((engine_reports.get("doclayout_yolo") or {}).get("status") or runtime_capabilities.get("doclayout_yolo") or "unknown"),
            "paddleocr": str((engine_reports.get("paddleocr") or {}).get("status") or runtime_capabilities.get("paddleocr") or "unknown"),
            "tesseract": str((engine_reports.get("tesseract") or {}).get("status") or runtime_capabilities.get("tesseract") or "unknown"),
            "donut": str((engine_reports.get("donut") or {}).get("status") or runtime_capabilities.get("donut") or "unknown"),
            "document_models_ready": bool(document_models.get("ready")),
        }
        return {
            "ready": ready,
            "runtime_mode": merged_capabilities["runtime_mode"],
            "device": merged_capabilities["device"],
            "gpu_preferred": merged_capabilities["gpu_preferred"],
            "gpu_available": merged_capabilities["gpu_available"],
            "bootstrap_report": bootstrap_report or {},
            "runtime_capabilities": merged_capabilities,
        }

    def _persist_report(self, report: dict[str, Any]) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    def _load_report(self) -> dict[str, Any]:
        if not self.report_path.exists():
            return {}
        try:
            return json.loads(self.report_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
