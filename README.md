# Autonomous Job Application Ecosystem

A local-first, single-user AI platform that ingests your career data (resumes, cover letters, prompts), monitors job listings, generates tailored LaTeX resumes and cover letters using LLMs, and stages or automates job applications with human-in-the-loop review guardrails.

Built with **FastAPI**, **React/Vite**, **Temporal**, **PostgreSQL + pgvector**, **MinIO**, and **OpenAI** (with optional Gemini support). Everything runs locally via **Docker Compose**.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [API Keys You Need](#api-keys-you-need)
- [Quick Start](#quick-start)
- [Step-by-Step Setup](#step-by-step-setup)
- [Configuration Reference](#configuration-reference)
- [Using the Platform](#using-the-platform)
- [Running the Smoke Test](#running-the-smoke-test)
- [Using Your Own Corpus](#using-your-own-corpus)
- [Repository Layout](#repository-layout)
- [Running Without Docker (Advanced)](#running-without-docker-advanced)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)

---

## Architecture Overview

```
┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
│   Frontend   │   │   FastAPI    │   │  Temporal Server  │
│  React/Vite  │──▶│   Backend    │──▶│  (Workflow Engine) │
│  Dashboard   │   │              │   └──────────────────┘
└──────────────┘   └──────┬───────┘           │
                          │                   ▼
                    ┌─────┴──────┐   ┌──────────────────┐
                    │ PostgreSQL │   │  Temporal Workers │
                    │ + pgvector │   │  (Main + DocIntel)│
                    └────────────┘   └──────────────────┘
                    ┌────────────┐
                    │   MinIO    │
                    │ (Artifacts)│
                    └────────────┘
```

| Component | Purpose |
|-----------|---------|
| **API** (FastAPI) | REST API for all operations — profiles, jobs, generation, applications, dashboard |
| **Main Worker** (Temporal) | Runs async workflows — corpus ingestion, resume/cover letter generation, application execution |
| **Document Worker** (Temporal) | Heavy document intelligence — OCR, layout analysis, profile fusion (optional, needs GPU) |
| **Frontend** (React/Vite) | Operator dashboard for monitoring jobs, reviewing drafts, approving applications |
| **PostgreSQL + pgvector** | Primary database with vector embedding support for semantic retrieval |
| **MinIO** | S3-compatible object store for generated artifacts (PDFs, HTML previews) |
| **Temporal** | Durable workflow engine that orchestrates multi-step pipelines with retry/recovery |

---

## Prerequisites

You need the following installed on your machine before starting:

| Requirement | Minimum Version | How to Get It |
|-------------|----------------|---------------|
| **Docker Desktop** | 4.x+ | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| **Docker Compose** | v2 (included with Docker Desktop) | Comes with Docker Desktop |
| **Git** | Any recent version | [git-scm.com](https://git-scm.com/) |
| **PowerShell** | 5.1+ (Windows) or pwsh 7+ (macOS/Linux) | Pre-installed on Windows; [Install pwsh](https://learn.microsoft.com/en-us/powershell/scripting/install/installing-powershell) |

**Hardware recommendations:**
- **RAM:** 8 GB minimum, 16 GB recommended (Docker containers + Postgres + Temporal add up)
- **Disk:** ~5 GB free for Docker images and data volumes
- **GPU (optional):** Only needed if you want to run the document-intelligence worker with local ML models

> **Note for macOS/Linux users:** The helper scripts (`.ps1`) require PowerShell. Install `pwsh` via Homebrew (`brew install powershell`) or your package manager, then run scripts with `pwsh ./start-platform.ps1`.

---

## API Keys You Need

### Required

| Service | Variable | How to Get It | Free Tier? |
|---------|----------|---------------|------------|
| **OpenAI** | `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) — sign up, go to API Keys, create a new secret key | Pay-as-you-go (no free tier for API, but low cost) |

The platform uses OpenAI for:
- Generating tailored resume and cover letter content
- Parsing and understanding job descriptions
- Embedding generation for semantic retrieval
- Document analysis (when `DOCUMENT_AI_PROVIDER=openai`)

> **No API key?** The system falls back to deterministic heuristic generation for local development, so you can explore the platform without spending money. LLM-powered features just won't produce real tailored output.

### Optional

| Service | Variable | Purpose | How to Get It |
|---------|----------|---------|---------------|
| **Google Gemini** | `GEMINI_API_KEY` | Alternative document AI provider | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| **SMTP (Email)** | `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` | Email notifications for application status | Your email provider's SMTP settings |
| **Slack** | `SLACK_WEBHOOK_URL` | Slack notifications | [api.slack.com/messaging/webhooks](https://api.slack.com/messaging/webhooks) |

---

## Quick Start

If you just want to get it running as fast as possible:

```powershell
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/AI-Powered-Job-Application-Ecosystem.git
cd AI-Powered-Job-Application-Ecosystem

# 2. Create your .env from the template
Copy-Item .env.example .env

# 3. Edit .env and add your OpenAI API key (line 20)
notepad .env
# Change: OPENAI_API_KEY=your-openai-api-key
# To:     OPENAI_API_KEY=sk-proj-your-actual-key-here

# 4. Start everything (builds containers, starts all services)
.\start-platform.ps1

# 5. Open the dashboard
# Dashboard:   http://localhost:5183
# API docs:    http://localhost:8013/docs
# Temporal UI: http://localhost:8080
# MinIO:       http://localhost:9001
```

---

## Step-by-Step Setup

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/AI-Powered-Job-Application-Ecosystem.git
cd AI-Powered-Job-Application-Ecosystem
```

### 2. Create Your Environment File

```powershell
Copy-Item .env.example .env
```

### 3. Configure Your `.env`

Open `.env` in any text editor and update these values:

**Must change:**

| Variable | What to Set |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key (starts with `sk-proj-...`) |
| `AUTH_SECRET` | A long random string for session signing — generate one with `python -c "import secrets; print(secrets.token_urlsafe(64))"` or any password generator |

**Can leave as defaults for local development:**

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@postgres:5432/job_ecosystem` | Docker internal DB connection |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `minioadmin` / `minioadmin` | Default MinIO dev credentials |
| `API_HOST_PORT` | `8013` | Port the API is exposed on your machine |
| `FRONTEND_HOST_PORT` | `5183` | Port the dashboard is exposed on your machine |

### 4. Start Docker Desktop

Make sure Docker Desktop is running and using **Linux containers** (default on macOS/Linux; on Windows, check the system tray icon).

### 5. Launch the Platform

```powershell
.\start-platform.ps1
```

This script will:
1. Verify Docker and Docker Compose are available
2. Create `.env` from `.env.example` if it doesn't exist
3. Start infrastructure services (Postgres, MinIO, Temporal, Temporal UI)
4. Wait for Postgres to be ready and enable the `pgvector` extension
5. Build and start application services (API, Worker, Frontend)
6. Wait for the API health check to pass
7. Print URLs for all services

**First run takes 5-10 minutes** (downloading Docker images + building). Subsequent starts are much faster.

### 6. Verify It's Working

Open these URLs in your browser:

| Service | URL | What You'll See |
|---------|-----|-----------------|
| **Dashboard** | http://localhost:5183 | React operator dashboard |
| **API Docs** | http://localhost:8013/docs | Interactive Swagger/OpenAPI docs |
| **Temporal UI** | http://localhost:8080 | Workflow execution monitor |
| **MinIO Console** | http://localhost:9001 | Object storage browser (login: `minioadmin` / `minioadmin`) |

### 7. Run the Smoke Test (Optional)

```powershell
.\smoke-test.ps1
```

This drives the full pipeline end-to-end using sample data: ingests the sample corpus, creates a job, generates a resume + cover letter, creates an application plan, and starts a run.

---

## Configuration Reference

All configuration is done through environment variables in `.env`. Here is the full list:

<details>
<summary><strong>Click to expand full variable reference</strong></summary>

### Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Environment name |
| `AUTH_SECRET` | — | **Set this!** Random string for session/token signing |
| `AUTH_SESSION_DAYS` | `30` | Session token lifetime |

### Ports

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PORT` | `8000` | API port inside the container |
| `API_HOST_PORT` | `8013` | API port on your machine |
| `FRONTEND_PORT` | `5183` | Frontend port inside the container |
| `FRONTEND_HOST_PORT` | `5183` | Frontend port on your machine |
| `TEMPORAL_UI_HOST_PORT` | `8080` | Temporal UI port on your machine |
| `MINIO_CONSOLE_HOST_PORT` | `9001` | MinIO console port on your machine |

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@postgres:5432/job_ecosystem` | PostgreSQL connection string |

### Temporal

| Variable | Default | Description |
|----------|---------|-------------|
| `TEMPORAL_TARGET` | `temporal:7233` | Temporal server gRPC address |
| `TEMPORAL_NAMESPACE` | `default` | Temporal namespace |

### MinIO (Object Storage)

| Variable | Default | Description |
|----------|---------|-------------|
| `MINIO_ENDPOINT` | `minio:9000` | MinIO API endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `job-artifacts` | Bucket name for artifacts |

### OpenAI

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | **Required for AI features.** Your OpenAI API key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API base URL |
| `OPENAI_PRIMARY_MODEL` | `gpt-5.4` | Primary generation model |
| `OPENAI_REVIEW_MODEL` | `gpt-5-mini` | Review/verification model |
| `OPENAI_PARSER_MODEL` | `gpt-5-nano` | Parsing/extraction model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` | Text embedding model |

### Gemini (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCUMENT_AI_PROVIDER` | `openai` | `openai` or `gemini` |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta` | Gemini API base URL |
| `GEMINI_PARSER_MODEL` | `gemini-2.5-flash` | Gemini model for document parsing |

### Notifications (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_FROM` | — | Sender email address |
| `SMTP_HOST` | — | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` | — | SMTP login username |
| `SMTP_PASSWORD` | — | SMTP login password |
| `SLACK_WEBHOOK_URL` | — | Slack incoming webhook URL |

### Browser Bridge

| Variable | Default | Description |
|----------|---------|-------------|
| `BROWSER_BRIDGE_URL` | `http://host.docker.internal:8877` | Browser automation bridge URL |
| `BROWSER_BRIDGE_PORT` | `8877` | Browser bridge port |

</details>

---

## Using the Platform

### Workflow Overview

1. **Ingest your corpus** — Upload resumes, cover letters, and prompt files that represent your career history
2. **Approve evidence** — Review and approve ingested fragments so they become available for retrieval
3. **Add/monitor jobs** — Create job entries manually or through source connectors (Seek, LinkedIn, etc.)
4. **Generate documents** — The AI generates tailored resumes and cover letters for specific jobs using your approved evidence
5. **Review & approve** — Review generated documents before they're used in applications
6. **Apply** — Create application plans and execute them (with review gates for sensitive sources)

### Key API Endpoints

All endpoints are documented interactively at `http://localhost:8013/docs`. Key ones:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/corpus/ingest` | POST | Ingest corpus files |
| `/api/v1/corpus/evidence` | GET | List evidence fragments |
| `/api/v1/jobs` | POST | Create a job |
| `/api/v1/generation/requests` | POST | Generate resume + cover letter |
| `/api/v1/applications/plans` | POST | Create application plan |
| `/api/v1/applications/runs` | POST | Start application run |
| `/api/v1/dashboard/overview` | GET | Dashboard summary |

---

## Running the Smoke Test

The smoke test uses the sample corpus under `sample-data/corpus` and drives the full pipeline:

```powershell
.\smoke-test.ps1
```

It will:
1. Wait for the API to be healthy
2. Ingest sample career documents (DevOps resume, cloud cover letter, tailoring prompts)
3. Approve all ingested evidence fragments
4. Create a sample job posting (Cloud DevOps Engineer at ExampleCo)
5. Generate a tailored resume and cover letter
6. Create an application plan
7. Start an application run
8. Fetch the dashboard overview

---

## Using Your Own Corpus

1. Place your files under `private-data/corpus/`:

   ```
   private-data/corpus/
   ├── resumes/          # Your resume files (.md, .tex, .pdf, .docx, .txt)
   ├── cover-letters/    # Your cover letter files
   └── prompts/          # Tailoring prompt files (.txt)
   ```

2. Place custom LaTeX templates under `private-data/templates/`.

3. Ingest your corpus:

   ```powershell
   .\import-corpus.ps1 -HostPath .\private-data\corpus -RoleHint Cloud,DevOps
   ```

4. Register custom templates:

   ```powershell
   .\register-template.ps1 -Name my-resume -DocumentKind resume -HostPath .\private-data\templates\resume.tex.j2
   .\register-template.ps1 -Name my-cover -DocumentKind cover_letter -HostPath .\private-data\templates\cover.tex.j2
   ```

5. Approve imported evidence via the API or helper script.

> **Important:** Keep your corpus and templates inside the repo directory so the Docker-mounted containers can access them. The `private-data/` directory is gitignored and stays local.

---

## Repository Layout

```
.
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI app and route handlers
│   │   ├── core/          # Configuration (Pydantic Settings)
│   │   ├── db/            # Database session, initialization
│   │   ├── models/        # SQLAlchemy ORM entities
│   │   ├── schemas/       # Pydantic request/response models
│   │   ├── services/      # Business logic (generation, retrieval, rendering, etc.)
│   │   ├── connectors/    # Job source integrations (Seek, LinkedIn, APSJobs, etc.)
│   │   ├── workflows/     # Temporal workflow and activity definitions
│   │   ├── templates/     # Default Jinja2/LaTeX templates
│   │   ├── worker.py      # Main Temporal worker entry point
│   │   └── document_worker.py  # Document intelligence worker
│   └── tests/             # Unit tests
├── frontend/
│   └── src/               # React/Vite dashboard (TypeScript)
├── infra/
│   ├── docker/            # Dockerfiles (API, document worker, frontend)
│   └── renderer/          # Puppeteer HTML-to-PDF renderer (Node.js)
├── sample-data/
│   └── corpus/            # Sample files for smoke testing
├── private-data/          # Your personal data (gitignored)
├── artifacts/             # Generated outputs (gitignored)
├── docker-compose.yml     # Full stack definition
├── pyproject.toml         # Python dependencies
├── .env.example           # Environment variable template
├── start-platform.ps1     # One-command startup script
├── smoke-test.ps1         # End-to-end smoke test
├── import-corpus.ps1      # Corpus import helper
└── register-template.ps1  # Template registration helper
```

---

## Running Without Docker (Advanced)

If you want to run services individually for development:

### Backend

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

# Install dependencies
pip install -e ".[dev]"

# For document intelligence features (optional, large download):
pip install -e ".[document_intelligence]"

# Install Playwright browsers
playwright install chromium

# Start the API
python -m backend.app.api.main

# In another terminal, start the main worker
python -m backend.app.worker

# In another terminal (optional), start the document worker
python -m backend.app.document_worker
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Infrastructure

You still need Postgres, MinIO, and Temporal running. The easiest way is to start just the infra via Docker:

```bash
docker compose up -d postgres minio temporal temporal-ui
```

### Tests

```bash
pytest
```

---

## Troubleshooting

### Docker Desktop is not running

```powershell
# Let the script try to start Docker Desktop for you:
.\start-platform.ps1 -StartDockerDesktop

# If Docker is in a bad state, try the recovery flow:
.\start-platform.ps1 -RecoverDocker
```

### Port conflicts

If default ports are in use, change them in `.env`:

```ini
API_HOST_PORT=8013
FRONTEND_HOST_PORT=5183
TEMPORAL_UI_HOST_PORT=8080
MINIO_CONSOLE_HOST_PORT=9001
```

### Rebuild containers after code changes

```powershell
.\start-platform.ps1
# Or manually:
docker compose up --build -d api worker frontend
```

### Skip rebuilding (use existing images)

```powershell
.\start-platform.ps1 -NoBuild
```

### View logs

```powershell
docker compose logs api --tail 100 -f        # API logs
docker compose logs worker --tail 100 -f     # Worker logs
docker compose logs frontend --tail 100 -f   # Frontend logs
```

### Reset everything

```powershell
docker compose down -v
Remove-Item -Recurse -Force postgres-data, minio-data, artifacts
.\start-platform.ps1
```

---

## Security Notes

- **Never commit your `.env` file** — it is already in `.gitignore`
- **The `private-data/` directory** contains personal career documents and is gitignored
- **The `artifacts/` directory** may contain generated resumes with personal info and is gitignored
- Government source connectors (APSJobs, Careers.Vic) are permanently review-gated as a safety measure
- The `AUTH_SECRET` in `.env.example` is a placeholder — always generate a unique one
- Default database and MinIO credentials (`postgres`/`minioadmin`) are fine for local development but should be changed for any network-exposed deployment

---

## License

This project is for personal use. See the repository for license details.
