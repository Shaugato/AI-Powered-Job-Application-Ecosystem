import logging
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.routes import applications, artifacts, auth, base_profiles, corpus, dashboard, generation, health, ingestion, integrations, jobs, learning, memory, notifications, prompts, review_queue, runtime, search_profiles
from backend.app.core.config import get_settings
from backend.app.db.init_db import init_db
from backend.app.services.bootstrap import bootstrap_defaults


settings = get_settings()
logger = logging.getLogger(__name__)


def _allowed_origins() -> list[str]:
    origins = {
        settings.frontend_base_url.rstrip("/"),
        "http://localhost:5183",
        "http://127.0.0.1:5183",
    }
    parsed = urlparse(settings.frontend_base_url)
    if parsed.scheme and parsed.port:
        host = parsed.hostname or "localhost"
        sibling = "127.0.0.1" if host == "localhost" else "localhost"
        origins.add(f"{parsed.scheme}://{sibling}:{parsed.port}")
    return sorted(origin for origin in origins if origin)


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Internal server error: {type(exc).__name__}"})


app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(base_profiles.router, prefix=settings.api_v1_prefix)
app.include_router(search_profiles.router, prefix=settings.api_v1_prefix)
app.include_router(prompts.router, prefix=settings.api_v1_prefix)
app.include_router(corpus.router, prefix=settings.api_v1_prefix)
app.include_router(memory.router, prefix=settings.api_v1_prefix)
app.include_router(jobs.router, prefix=settings.api_v1_prefix)
app.include_router(ingestion.router, prefix=settings.api_v1_prefix)
app.include_router(integrations.router, prefix=settings.api_v1_prefix)
app.include_router(generation.router, prefix=settings.api_v1_prefix)
app.include_router(applications.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
app.include_router(artifacts.router, prefix=settings.api_v1_prefix)
app.include_router(notifications.router, prefix=settings.api_v1_prefix)
app.include_router(learning.router, prefix=settings.api_v1_prefix)
app.include_router(review_queue.router, prefix=settings.api_v1_prefix)
app.include_router(runtime.router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
def startup() -> None:
    init_db()
    bootstrap_defaults()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.api.main:app", host="0.0.0.0", port=settings.api_port, reload=True)
