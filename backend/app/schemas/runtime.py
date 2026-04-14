from __future__ import annotations

from pydantic import BaseModel


class DocumentRuntimeStatus(BaseModel):
    ready: bool
    runtime_mode: str
    device: str
    gpu_preferred: bool
    gpu_available: bool
    bootstrap_report: dict
    runtime_capabilities: dict
