from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "Autonomous Job Application Ecosystem"
    api_v1_prefix: str = "/api/v1"
    api_port: int = 8000
    frontend_port: int = 5183
    frontend_base_url: str = "http://localhost:5183"
    backend_base_url: str = "http://localhost:8013"
    auth_secret: str = "change-me-local-auth-secret"
    auth_session_days: int = 30

    database_url: str = "sqlite:///./job_ecosystem.sqlite3"
    temporal_target: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_main_task_queue: str = "job-ecosystem"
    temporal_document_task_queue: str = "job-ecosystem-document-intel"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "job-artifacts"

    artifacts_dir: Path = Field(default=Path("artifacts"))
    private_data_dir: Path = Field(default=Path("private-data"))
    corpus_upload_dir: Path = Field(default=Path("private-data/corpus/uploads"))
    library_dir: Path = Field(default=Path("private-data/library"))
    template_upload_dir: Path = Field(default=Path("private-data/templates"))
    integration_data_dir: Path = Field(default=Path("private-data/integrations"))
    browser_run_dir: Path = Field(default=Path("artifacts/browser-runs"))

    openai_api_key: str | None = None
    browser_capture_host: str = "host.docker.internal"
    browser_capture_base_port: int = 9333
    browser_bridge_url: str = "http://host.docker.internal:8877"
    browser_bridge_timeout_seconds: int = 5
    openai_base_url: str = "https://api.openai.com/v1"
    openai_primary_model: str = "gpt-5.4"
    openai_review_model: str = "gpt-5-mini"
    openai_parser_model: str = "gpt-5-nano"
    openai_embedding_model: str = "text-embedding-3-large"
    openai_multimodal_model: str = "gpt-5.4"
    document_ai_provider: str = "openai"
    document_gpu_preferred: bool = True
    document_runtime_mode: str = "dual"
    document_confidence_threshold: float = 0.78
    document_review_threshold: float = 0.58
    document_max_repair_attempts: int = 3
    retriever_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    layoutlm_model_name: str = "microsoft/layoutlmv3-base"
    donut_model_name: str = "naver-clova-ix/donut-base-finetuned-docvqa"
    doclayout_model_repo_id: str = "juliozhao/DocLayout-YOLO-DocStructBench"
    doclayout_model_filename: str = "doclayout_yolo_docstructbench_imgsz1024.pt"
    document_worker_cache_dir: Path = Field(default=Path("private-data/model-cache"))
    document_bootstrap_on_start: bool = True
    document_fail_fast_on_startup: bool = True
    renderer_node_bin: str = "node"
    renderer_script_path: Path = Field(default=Path("infra/renderer/render-resume.mjs"))
    renderer_package_dir: Path = Field(default=Path("infra/renderer"))
    renderer_timeout_seconds: int = 90
    puppeteer_executable_path: str | None = None
    legacy_tex_enabled: bool = True
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_parser_model: str = "gemini-2.5-flash"

    email_from: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    slack_webhook_url: str | None = None

    app_daily_cap: int = 15
    timezone: str = "Australia/Sydney"
    playwright_headless: bool = True
    playwright_timeout_ms: int = 15000


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    settings.private_data_dir.mkdir(parents=True, exist_ok=True)
    settings.corpus_upload_dir.mkdir(parents=True, exist_ok=True)
    settings.library_dir.mkdir(parents=True, exist_ok=True)
    settings.template_upload_dir.mkdir(parents=True, exist_ok=True)
    settings.integration_data_dir.mkdir(parents=True, exist_ok=True)
    settings.browser_run_dir.mkdir(parents=True, exist_ok=True)
    settings.document_worker_cache_dir.mkdir(parents=True, exist_ok=True)
    settings.renderer_package_dir.mkdir(parents=True, exist_ok=True)
    return settings

