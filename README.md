# 🧠 SourceDesc AI

> **Enterprise Data Cataloging & Metadata Enrichment Platform powered by LLMs**

SourceDesc AI connects to your enterprise data sources, uses LLMs to automatically generate high-quality business descriptions, PII classifications, domain tags, and glossary suggestions — then syncs the enriched metadata directly into **Microsoft Purview** and **Databricks Unity Catalog**.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        SourceDesc AI Platform                   │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────────┐  │
│  │  Source      │   │  Profiling & │   │  AI Enrichment    │  │
│  │  Connectors  │──▶│  Sampling    │──▶│  Engine (LLM)     │  │
│  │  (+ MCP)     │   │  Engine      │   │  Azure OAI/Ollama │  │
│  └──────────────┘   └──────────────┘   └────────┬──────────┘  │
│                                                  │              │
│                                        ┌─────────▼──────────┐  │
│                                        │  Metadata Store    │  │
│                                        │  (PostgreSQL+Redis)│  │
│                                        └─────────┬──────────┘  │
│                                                  │              │
│                                        ┌─────────▼──────────┐  │
│                                        │  Review UI         │  │
│                                        │  (FastAPI + React) │  │
│                                        └─────────┬──────────┘  │
│                                                  │              │
│                              ┌───────────────────┼──────────┐  │
│                    ┌─────────▼──────┐   ┌────────▼────────┐ │  │
│                    │ MS Purview API │   │ Databricks UC   │ │  │
│                    └───────────────┘   └─────────────────┘ │  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Features

- **Multi-source connectors** — SQL Server, PostgreSQL, MySQL, Oracle, Snowflake, MongoDB, CosmosDB, Cassandra, ADLS, S3, GCS, Salesforce, SAP, ServiceNow, Kafka
- **AI enrichment** — Table/column descriptions, glossary terms, sensitivity classification, domain tagging
- **LLM flexibility** — Azure OpenAI, OpenAI, or local Ollama models
- **Human-in-the-loop** — Review workspace with confidence scoring before any sync
- **Catalog sync** — Microsoft Purview (Data Map API) + Databricks Unity Catalog
- **PII detection** — Microsoft Presidio local scanning before LLM
- **Incremental processing** — Schema hash + row count drift detection
- **MCP connector support** — Wraps DBHub, AnythingMCP, official MCP servers
- **Production ready** — Retry/circuit breaker, audit logs, multi-tenancy, cost estimation

---

## 📁 Project Structure

```
sourcedesc-ai/
├── backend/
│   ├── connectors/          # Source adapters (relational, nosql, storage, saas, mcp)
│   ├── profiler/            # Schema extractor, sampler, PII detector, change detector
│   ├── enrichment/          # LLM router, prompt templates, enricher, validator, few-shot
│   ├── sync/                # Purview client, Unity Catalog client
│   ├── api/                 # FastAPI routers
│   ├── models/              # SQLAlchemy ORM models
│   ├── workers/             # Celery tasks
│   └── utils/               # Resilience, secrets, logging
├── frontend/                # React 18 + TypeScript + Tailwind
├── infra/
│   ├── docker-compose.yml
│   └── helm/
└── tests/
```

---

## ⚡ Quick Start

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker + Docker Compose
- PostgreSQL 16
- Redis 7

### 1. Clone & Setup

```bash
git clone https://github.com/Bhushan-Khachane/sourcedesc-ai.git
cd sourcedesc-ai
cp .env.example .env
# Edit .env with your credentials
```

### 2. Start with Docker Compose

```bash
docker-compose up -d
```

### 3. Run locally (dev)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000

# Worker
celery -A workers.enrichment_pipeline worker --loglevel=info

# Frontend
cd frontend
npm install && npm run dev
```

API docs: http://localhost:8000/docs  
UI: http://localhost:3000

---

## 🔧 Configuration

See `.env.example` for all configuration options including:
- LLM provider selection (Azure OpenAI / OpenAI / Ollama)
- Secrets backend (Azure Key Vault / AWS Secrets Manager / env vars)
- Purview account name
- Databricks workspace host + warehouse ID
- Sampling rules and PII settings

---

## 📖 Documentation

- [Architecture Deep Dive](docs/architecture.md)
- [Connector Guide](docs/connectors.md)
- [LLM Configuration](docs/llm-config.md)
- [Purview Sync](docs/purview-sync.md)
- [Unity Catalog Sync](docs/unity-catalog-sync.md)
- [Production Deployment](docs/deployment.md)
- [Known Limitations](docs/known-limitations.md)

---

## 🛡️ Security

- All source credentials via Azure Key Vault / AWS Secrets Manager
- Read-only source connections enforced at DB level
- Microsoft Presidio for local PII detection (data never leaves environment)
- Azure AD / OAuth2 PKCE for UI auth
- RBAC: Admin, DataSteward, Engineer, Viewer roles
- Full audit log for every enrichment and sync action

---

## 📄 License

MIT License — see [LICENSE](LICENSE)
