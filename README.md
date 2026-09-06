# Atmos

A continuously updated technology-intelligence platform observing the AI engineering ecosystem.

Atmos watches the public internet for meaningful changes in the AI landscape, detects shifts in technology momentum, and produces evidence-backed insights — not dashboards, not news feeds, not chatbots.

**Live demo:** [atmos-mu.vercel.app](https://atmos-mu.vercel.app)

---

## What It Does

Atmos runs a daily pipeline that ingests data from GitHub, computes statistical signals, classifies each technology into a weather state, and serves everything through a fast API to a Next.js frontend.

**The core loop:**

```
Observe → Detect → Classify → Explain → Explore
```

- **Observe:** Ingests star counts, forks, commits, releases, contributors, and issues from 144 repositories across 45 AI technologies.
- **Detect:** Computes velocity (7-day and 28-day), acceleration, anomaly z-scores, breadth, persistence, and event intensity.
- **Classify:** Assigns each technology a weather state — Hot, Emerging, Stable, Cooling, Breaking, or Storm — based on its measured signals, never hardcoded.
- **Explain:** Generates human-readable explanations tied to the data that drove the classification.
- **Explore:** Presents everything through an interactive frontend with Trends, Explore (graph), and Research pages.

---

## Weather States

| State | Glyph | Meaning |
|-------|-------|---------|
| Hot | 🔥 | Sustained high growth well above its own baseline |
| Emerging | 🌱 | Young and accelerating from a small base |
| Stable | 🌤 | Activity consistent with its own recent baseline |
| Cooling | ❄️ | Activity decaying relative to its own baseline |
| Breaking | ⚡ | A discrete event just moved this technology sharply |
| Storm | 🌪 | Violent, unstable activity — direction unresolved |

Weather states are **computed from measured signals**, never assigned by hand.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS |
| Backend API | FastAPI, Pydantic, SQLAlchemy |
| Database | PostgreSQL (Neon) |
| Workers | Python 3.14, httpx, tenacity, NumPy |
| Migrations | Alembic |
| CI/CD | GitHub Actions, Railway, Vercel |

**Cost: $0** — built entirely on free-tier infrastructure.

---

## Project Structure

```
Atmos/
├── backend/                  # FastAPI read API + domain models
│   ├── internetweather/
│   │   ├── api/              # FastAPI app + route handlers
│   │   ├── analysis/         # Signal computation, weather state classifier
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic API schemas
│   │   ├── services/         # Business logic (cards, research)
│   │   ├── integrations/     # External API clients
│   │   ├── research/         # Research engine
│   │   └── config.py         # Settings via pydantic-settings
│   ├── alembic/              # Database migrations
│   └── tests/                # Backend test suite (228 tests)
├── workers/                  # Background data pipeline
│   ├── github/               # GitHub metrics ingestion
│   ├── detection/            # Signal computation + weather classification
│   ├── seed/                 # Technology universe seeding
│   └── retention/            # Data lifecycle management
├── frontend/                 # Next.js application
│   ├── app/                  # Pages: Trends, Explore, Research
│   ├── components/           # UI components (trends, weather, research)
│   └── lib/                  # API client, formatting utilities
├── docs/                     # OpenAPI spec, architecture docs
├── .github/workflows/        # Daily pipeline (GitHub Actions)
├── Dockerfile                # Railway deployment
└── start.py                  # Production startup script
```

---

## Getting Started

### Prerequisites

- Python 3.14+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- A PostgreSQL database (Neon free tier works)

### 1. Clone and install

```bash
git clone https://github.com/Dhruv-Jain-2006/Atmos.git
cd Atmos

# Python dependencies
uv sync

# Frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your database URLs and GitHub token:

```env
# Neon pooled URL (for the API)
DATABASE_URL=postgresql+psycopg://user:pass@ep-xxx-pooler.neon.tech/internetweather?sslmode=require

# Neon direct URL (for workers and migrations)
DATABASE_URL_DIRECT=postgresql+psycopg://user:pass@ep-xxx.neon.tech/internetweather?sslmode=require

# GitHub PAT (fine-grained, public read only)
GITHUB_TOKEN=ghp_xxxxx
```

### 3. Run database migrations

```bash
uv run alembic upgrade head
```

### 4. Seed the technology universe

```bash
uv run python -m workers.seed.bootstrap
```

This creates 45 technologies across 7 subdomains with weighted repository relationships.

### 5. Start the backend API

```bash
uv run uvicorn backend.internetweather.api.app:app --reload --port 8000
```

API docs at [localhost:8000/docs](http://localhost:8000/docs).

### 6. Start the frontend

```bash
cd frontend && npm run dev
```

Frontend at [localhost:3000](http://localhost:3000).

---

## Running the Daily Pipeline

The pipeline runs automatically via GitHub Actions at **5:45 PM IST** every day. It can also be triggered manually.

### Full pipeline

```bash
# Sync GitHub metrics (all repos)
uv run python -m workers.github.sync_metrics --budget 800

# Compute signals + classify weather states
uv run python -m workers.detection.compute_signals
```

### What happens in the pipeline

1. **Sync metrics** — Fetches stars, forks, commits, releases, contributors, and issues for each tracked repository. Writes daily metric rows. Stale repos get "snapshot" rows so `compute_signals` always has today's data.
2. **Verify ingestion** — Checks all 144 repos have today's metric row, no duplicates.
3. **Compute signals** — Calculates velocity, acceleration, anomaly z-scores, and all seven signal dimensions.
4. **Classify** — Assigns weather states using the decision tree classifier.
5. **Verify detection** — Confirms all 45 technologies have fresh signals.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness check + degradation status |
| GET | `/api/vocabulary` | Weather state glyphs, labels, meanings |
| GET | `/weather` | Global conditions snapshot |
| GET | `/api/trends` | Full Trends page data (bands + events) |
| GET | `/api/technologies` | All tracked technologies |
| GET | `/api/technologies/{slug}` | Technology detail + signals + repos |
| GET | `/api/technologies/{slug}/history` | Historical signal data |
| GET | `/api/technologies/{slug}/related` | Related technologies |
| GET | `/api/events` | Detected ecosystem events |
| GET | `/api/events/{event_id}` | Event detail with evidence |
| POST | `/api/research` | Start an asynchronous research job |
| GET | `/api/research/{id}` | Research job status |
| POST | `/api/research/{id}/chat` | Chat with research copilot |

---

## Signal Dimensions

Each technology is measured across seven dimensions:

| Dimension | What It Measures |
|-----------|-----------------|
| **Velocity** | Rate of change in star count (7-day and 28-day windows) |
| **Acceleration** | Whether velocity is increasing or decreasing |
| **Anomaly** | Z-score of current activity vs. historical baseline |
| **Breadth** | How many repositories are contributing to the signal |
| **Persistence** | How consistently the signal appears over time |
| **Event Intensity** | Magnitude of discrete events (releases, spikes) |
| **Evidence Depth** | How many independent data sources confirm the signal |

---

## Database Schema

Key tables:

| Table | Purpose |
|-------|---------|
| `technology` | 45 tracked AI technologies with metadata |
| `technology_repository` | Links technologies to GitHub repos with weights |
| `repository` | GitHub repository metadata + sync state |
| `repository_metric_daily` | Daily snapshots: stars, forks, commits, releases, etc. |
| `technology_signal_daily` | Computed signals: velocity, acceleration, anomaly, etc. |
| `ecosystem_event` | Detected events: releases, star spikes, anomalies |
| `technology_relationship` | Edges between technologies (depends_on, co_occurs, etc.) |

---

## Testing

```bash
# Run all 228 tests
uv run pytest backend/tests/ -x -q

# Run a specific test file
uv run pytest backend/tests/test_detection.py -x -q

# Run with verbose output
uv run pytest backend/tests/ -v
```

### Linting

```bash
# Python
uv run ruff check backend/ workers/

# Frontend
cd frontend && npm run lint
```

---

## Deployment

### Frontend (Vercel)

Connected to `main` branch. Auto-deploys on push.

```bash
git push origin main  # triggers Vercel build
```

### Backend API (Railway)

Deployed via Dockerfile. The `start.py` script reads `$PORT` from Railway's environment.

```bash
# Railway handles this automatically on push to main
# Manual deploy:
railway up
```

### Daily Pipeline (GitHub Actions)

Runs on a cron schedule at `12:15 UTC` (5:45 PM IST). Can be triggered manually from the Actions tab with an optional `force_full_sync` flag.

---

## Architecture Principles

1. **The LLM is never the primary detector.** Statistical and ML methods run first. LLMs synthesize findings into human-readable explanations.
2. **Every claim carries an epistemic status.** `observation`, `inference`, `hypothesis`, or `unknown` — speculation is never presented as fact.
3. **The API is stateless and sub-second.** No ingestion, no classification, no LLM calls in the read path.
4. **The frontend never talks to external APIs.** Everything goes through Atmos's normalized API.
5. **Free tier by design.** Neon, Vercel, Railway, GitHub Actions — $0/month at portfolio scale.

---

## License

MIT
