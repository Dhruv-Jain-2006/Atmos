# Internet Weather — Project Context

## Product

Internet Weather is a continuously updated technology-intelligence platform.

It observes signals from the public internet, detects meaningful changes in the AI engineering ecosystem, investigates those changes across multiple independent sources, and produces evidence-backed insights explaining:

- What is changing?
- How significant is the change?
- Why might it be happening?
- What technologies are related?
- What evidence supports the conclusion?
- What should we watch next?

This is NOT:
- a generic AI chatbot
- a GitHub analytics dashboard
- a news aggregator
- a generic SaaS dashboard
- an LLM wrapper

The core product loop is:

OBSERVE → DETECT → INVESTIGATE → EXPLAIN → EXPLORE

---

# Initial Domain

V1 focuses on the AI Engineering ecosystem.

Subdomains:

1. Agentic AI
2. LLMs and model ecosystems
3. RAG and knowledge systems
4. AI infrastructure and inference
5. Multimodal AI
6. MLOps
7. AI security

The architecture must allow additional technology domains later without major rewrites.

---

# Core User Experience

Primary navigation:

1. Explore
2. Trends
3. Research

### Explore

Interactive AI-engineering technology ecosystem.

Users can:
- zoom
- pan
- search
- filter
- inspect technologies
- inspect relationships
- discover emerging technology clusters

### Trends

The primary discovery page.

Users see:
- trending technologies
- emerging technologies
- heating/cooling technologies
- major ecosystem events
- anomalies
- trend graphs

Hovering a technology/event displays a compact intelligence preview.

Clicking opens its deeper research experience.

### Research

Deep investigation experience.

A research page contains:
- executive finding
- observed signals
- historical timeline
- related technologies
- evidence
- sources
- confidence
- counter-evidence
- AI Research Copilot

The Research Copilot is contextual to the selected research topic.

It must be able to:
- explain
- compare
- explore relationships
- inspect history
- investigate causes
- query Internet Weather data
- cite evidence

It is NOT a generic chatbot.

---

# Core Interaction

Example:

User sees:

MCP ⚡

Hover:

- momentum
- signal changes
- weather state
- confidence
- short explanation

Click:

→ MCP research page

User sees:

"Why is MCP accelerating?"

Click:

Investigate

System performs research.

Then user can ask:

"Is this growth driven by a few repositories?"

The Research Copilot queries the backend's structured data and evidence sources and responds with traceable evidence.

---

# Data Philosophy

Do NOT scrape random GitHub data.

Every collected field must have a defined purpose.

GitHub is a developer-behavior sensor.

Relevant GitHub signals include:

- repository metadata
- topics
- languages
- stars
- star velocity
- forks
- fork velocity
- contributors
- contributor growth
- commits
- commit velocity
- releases
- repository creation
- issues
- pull requests
- dependencies
- README/description technology mentions
- repository relationships

We do NOT download entire repositories by default.

Use selective metadata and targeted content extraction.

The system should maintain a technology universe and discover relevant repositories rather than monitoring all GitHub repositories.

---

# Primary Data Sources

V1 primary sources:

- GitHub
- npm
- PyPI
- arXiv
- NVD/CVE
- Hugging Face

Secondary research sources:

- job data
- Stack Overflow
- news/web search

News/search should primarily be used to explain detected events rather than become the primary data source.

---

# Data Ingestion

Internet Weather is continuously observing, not continuously scraping.

Use multiple ingestion strategies:

### GitHub

Tracked repositories:
- webhooks where possible

Discovery:
- periodic API jobs

Metrics:
- periodic incremental updates

### npm / PyPI

Periodic incremental synchronization.

### arXiv

Periodic synchronization of newly published relevant papers.

### NVD

Incremental synchronization using modified-date windows.

### Hugging Face

Periodic synchronization of model/dataset ecosystem signals.

### News/search

On-demand when a detected event requires external investigation.

---

# Important Architecture Principle

Separate:

1. ingestion
2. normalization
3. aggregation
4. detection
5. research
6. presentation

Do NOT make the frontend directly query external APIs.

Do NOT make the LLM process raw internet data.

The pipeline is:

Internet
→ ingestion
→ normalized events
→ PostgreSQL
→ statistical/ML analysis
→ significant signals
→ research engine
→ evidence
→ LLM synthesis
→ frontend

---

# LLM Philosophy

The LLM must not be the primary detector.

Use deterministic/statistical/ML methods first.

Example:

100,000 raw events
→ aggregation
→ anomaly/trend detection
→ significant events
→ research
→ LLM synthesis

Avoid unnecessary LLM calls.

All generated findings should distinguish:

- OBSERVATION
- INFERENCE
- HYPOTHESIS
- UNKNOWN

Never present speculation as fact.

Every significant claim should have supporting evidence where possible.

---

# Proposed Technology Stack

## Frontend

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- Motion
- React Flow or a scalable graph renderer
- Recharts or another lightweight charting library

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy

## Database

- PostgreSQL
- Neon
- pgvector

Use one primary database initially.

Do NOT introduce additional databases unless justified.

## Cache

- Redis
- Upstash

## ML

- NumPy
- pandas
- scikit-learn
- SciPy
- statsmodels

## NLP / embeddings

- Hugging Face
- sentence-transformers

Prefer local/open-source models where practical.

## LLM

Design an abstraction so the application can use:

- Gemini API when available
- Ollama/local models as fallback

Never tightly couple application logic to one LLM provider.

---

# Backend Design

Logical components:

backend/
├── api/
├── services/
├── models/
├── repositories/
├── schemas/
├── integrations/
├── analysis/
└── research/

workers/
├── github/
├── npm/
├── pypi/
├── arxiv/
├── nvd/
├── huggingface/
├── normalization/
├── detection/
└── research/

The exact structure can evolve.

---

# API Philosophy

Frontend consumes Internet Weather's own normalized API.

Example endpoints:

GET /api/weather
GET /api/trends
GET /api/technologies
GET /api/technologies/{id}
GET /api/events
GET /api/events/{id}
GET /api/technologies/{id}/history
GET /api/technologies/{id}/relationships

Research:

POST /api/research
GET /api/research/{id}
POST /api/research/{id}/chat

Do not expose provider-specific APIs directly to the frontend.

---

# Research Jobs

Research can be asynchronous.

POST /api/research

returns:

{
  "research_id": "...",
  "status": "queued"
}

Possible states:

queued
collecting
analyzing
synthesizing
completed
failed

The frontend must never block waiting for a long research operation.

---

# Performance

Performance is a first-class requirement.

Avoid:
- unnecessary API calls
- duplicate ingestion
- large raw payload storage
- synchronous long-running requests
- repeated LLM calls
- fetching entire repositories
- unbounded graph rendering
- N+1 database queries

Use:
- incremental sync
- caching
- aggregation
- pagination
- background jobs
- rate limiting
- retries with backoff
- idempotent ingestion
- database indexes
- lazy loading
- graph virtualization/progressive loading

The application must be designed for free-tier constraints.

---

# Free Infrastructure Constraint

The project must be designed to run at $0 for portfolio-scale usage.

Preferred services:

- GitHub
- Neon PostgreSQL
- Upstash
- Cloudflare
- free API tiers
- open-source libraries
- local models where practical

Never add a paid dependency without explicit justification.

"Free" does not mean unlimited.

Respect:
- API rate limits
- storage limits
- compute limits
- token quotas

Build quota-aware ingestion.

---

# Frontend Design Direction

The visual identity should feel like:

scientific observatory
+
weather radar
+
technology intelligence system

NOT:
- generic AI SaaS
- generic dashboard
- excessive cards
- excessive gradients
- neon cyberpunk everywhere

Use:
- dark atmospheric interface
- subtle grid
- restrained glow
- strong typography
- data-driven animation
- smooth transitions
- negative space
- graph-centric interaction

Animations must communicate state or transitions.

---

# Weather States

Use a consistent semantic vocabulary:

🔥 HOT
🌱 EMERGING
🌤 STABLE
❄️ COOLING
⚡ BREAKING
🌪 STORM

Weather states must be computed from actual signals.

Do not hardcode them.

---

# Product Principle

The product should answer:

"What is changing in AI engineering right now?"

Then:

"Why?"

Then:

"Show me the evidence."

Then:

"What is connected to it?"

Then:

"What should I watch next?"

Everything we build should strengthen this loop.

---

# Development Rules

Before implementing a feature:

1. Understand the product purpose.
2. Define its backend data contract.
3. Define its performance implications.
4. Implement the smallest useful version.
5. Test it.
6. Avoid premature infrastructure.

Do not generate large amounts of boilerplate.

Do not add dependencies without a reason.

Do not replace working architecture just because another technology is trendy.

Prefer simple, observable, maintainable systems.

---

# Current Goal

Build the first vertical slice:

DATA SOURCE
→ GitHub ingestion
→ normalized database
→ technology signals
→ trend calculation
→ FastAPI API
→ Trends frontend
→ hover intelligence preview
→ technology research page
→ basic Research Copilot

The first vertical slice must work end-to-end before expanding to other data sources.