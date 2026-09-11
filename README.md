# ⚡ VajraTrace (वज्रट्रेस)
### Automated Multi-Chain Forensic Analytics & Real-Time Exchange Attribution Platform

[![Smart India Hackathon 2026](https://img.shields.io/badge/SIH%202026-Problem%20Statement%2026183-orange?style=for-the-badge&logo=target)](https://www.sih.gov.in/)
[![Theme: Blockchain & Cybersecurity](https://img.shields.io/badge/Theme-Blockchain%20%26%20Cybersecurity-red?style=for-the-badge&logo=shield)](https://cybercrime.gov.in/)
[![Team Servidor](https://img.shields.io/badge/Team-Servidor-blue?style=for-the-badge&logo=github)](https://github.com/atharva169/VajraTrace)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js 15](https://img.shields.io/badge/Next.js-15.0-black?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org)
[![React 19](https://img.shields.io/badge/React-19.0-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Neo4j 5](https://img.shields.io/badge/Neo4j-5.x-45818e?style=flat-square&logo=neo4j&logoColor=white)](https://neo4j.com)
[![Redis 7](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![XGBoost](https://img.shields.io/badge/XGBoost-2.0+-eb6100?style=flat-square&logo=python&logoColor=white)](https://xgboost.readthedocs.io)
[![SHAP](https://img.shields.io/badge/Explainability-SHAP-blueviolet?style=flat-square)](https://shap.readthedocs.io)
[![Cytoscape.js](https://img.shields.io/badge/Graph_Viz-Cytoscape.js-ff69b4?style=flat-square)](https://js.cytoscape.org/)
[![BSA 2023 §63](https://img.shields.io/badge/Court_Admissible-BSA%202023%20%C2%A763-success?style=flat-square)](#-legal-admissibility--court-compliance)

---

## 📌 Executive Summary

When Indian cyber fraud victims file complaints via the **National Cyber Crime Reporting Portal (NCRP / cybercrime.gov.in)** or the **1930 Citizen Helpline**, fraudulent fiat transactions can often be frozen in the "golden hour" through the **Citizen Financial Cyber Fraud Reporting and Management System (CFCFRMS)**. 

However, in modern cyber financial crimes—such as **pig-butchering (Sha Zhu Pan)**, **task fraud**, **fake investment schemes**, and **ransomware**—perpetrators instantly convert stolen funds into cryptocurrencies (primarily **USDT on TRON/Ethereum** or **Bitcoin**) and channel them through multi-hop peeling chains, mixer protocols, and cross-chain bridges before cashing out on Virtual Asset Service Providers (VASPs).

Existing commercial forensic software (e.g., Chainalysis, TRM Labs, Elliptic) imposes:
1. **Prohibitive Licensing Fees** ($50,000 – $100,000+ per analyst seat annually), rendering state-level cyber cells and district police stations unable to deploy them at scale.
2. **Data Sovereignty Concerns**, routing sensitive Indian Law Enforcement Agency (LEA) investigations through foreign cloud infrastructures.
3. **No Direct Legal Integration** with Indian statutory requirements like **Section 63 of the Bharatiya Sakshya Adhiniyam (BSA), 2023** (formerly Section 65B of the Indian Evidence Act) or automated Section 91/102 notices under BNSS/CrPC.

**VajraTrace** bridges this critical operational gap. It takes a victim-reported crypto address, autonomously traces fund flows across **Bitcoin (BTC)**, **Ethereum (ETH)**, and **TRON (TRX/TRC-20)** in real-time, clusters co-controlled wallets, detects cross-chain bridge hops, predicts fraud typologies with an **Elliptic++ trained XGBoost model**, generates an **autonomous LLM forensic narrative**, and produces **cryptographically verified, court-ready PDF evidence packages** and **VASP freeze requests** in under 60 seconds.

---

## 🎯 Problem Statement (SIH 2026 · PS 26183)

| Parameter | Details |
| :--- | :--- |
| **Problem Statement ID** | `26183` |
| **Problem Statement Title** | Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges from Victim-Reported Suspect Wallet Addresses through Automated Blockchain Analytics |
| **Nodal Ministry / Organization** | Ministry of Home Affairs (MHA) / Indian Cybercrime Coordination Centre (I4C) |
| **Theme** | Blockchain & Cybersecurity |
| **Category** | Software |
| **Team Name** | **Servidor** |

---

## 🌟 Key Innovations & System Features

### 1. Multi-Chain Real-Time Forensic Ingestion
- Ingests suspect addresses across **Bitcoin (BTC)**, **Ethereum (ETH)**, and **TRON (TRX/TRC-20)**.
- Normalizes disparate blockchain architectures (UTXO vs. Account-based) into unified graph edges and transfer records.
- In-memory & Redis multi-tier caching prevents API throttling while respecting upstream rate limits.

### 2. Multi-Heuristic Address Clustering Engine
- **Common-Input Ownership Heuristic (Multi-Input)**: Identifies co-spent UTXOs to map large wallet clusters belonging to the same cyber syndicate.
- **Peeling Chain Detection**: Tracks systematic peeling patterns where large illicit balances are stripped through single-output change transfers.
- **Deposit Address Reuse & Consolidation**: Identifies intermediary deposit wallets aggregating funds into known exchange hot/deposit wallets.
- **Cross-Chain Bridge Correlation**: Correlates cross-network hops (e.g., ETH $\to$ TRON) using temporal proximity windows ($\pm 60$ min) and USD-normalized transfer volumes ($\pm 5\%$ fee tolerance).

### 3. Explainable Machine Learning Risk Scoring (XGBoost + SHAP)
- Trained on the **Elliptic++ Dataset** (the academic standard benchmark for Bitcoin illicit transaction detection).
- Computes calibrated fraud probabilities (0.0 to 1.0) using 48+ graph topological, local, and aggregated transactional features.
- Provides **SHAP (SHapley Additive exPlanations)** values directly to the investigator, explaining *why* an address is risky (e.g., high mixer interaction ratio, short lifespan, anomalous velocity).
- Evaluated performance: **68.8% Precision, 60.4% Recall, 64.3% F1-score, and 0.677 Average Precision (PR-AUC)** on strict holdout test data.

### 4. Autonomous Agentic Forensic Reasoner (Groq / Llama 3.3 70B)
- Built-in autonomous forensic investigator driven by **Llama 3.3 70B** via Groq tool-calling.
- Functions through a tool-execution loop: checks curated VASP tags $\to$ queries cluster membership $\to$ evaluates bridge hops $\to$ requests ML risk scoring $\to$ writes an executive investigation narrative.
- **Deterministic Rule-Based Fallback**: If the LLM provider is offline or credentials are not supplied, a rule-based engine seamlessly executes the forensic steps so investigations never stall.

### 5. Court-Admissible Evidence Chain (BSA 2023 § 63 Compliant)
- Immutable, append-only hash-chained audit log.
- Each forensic step computes a cryptographic hash:
  $$\text{integrity\_hash} = \text{SHA-256}(\text{step\_number} \parallel \text{action} \parallel \text{result\_summary} \parallel \text{prev\_hash})$$
- Satisfies statutory digital evidence requirements under **Section 63 of the Bharatiya Sakshya Adhiniyam, 2023** (preventing evidence tampering in criminal proceedings).
- Verifiable with one click via the `/api/v1/trace/{id}/evidence?verify_integrity=true` endpoint.

### 6. Automated PDF Investigation Dossier & VASP Freeze Notices
- Generated via headless **WeasyPrint + Jinja2** with police/cyber-cell grade styling.
- Contains executive summary, case metadata, VASP attribution confidence rating, graph snapshot, SHAP feature importance plot, step-by-step audit trail, and an embedded QR code linking to the live verification hash.
- Generates pre-formatted **Section 91/102 Notice to VASP (Exchange Freeze Order)** for immediate transmission to compliance desks at Binance, WazirX, CoinDCX, KuCoin, etc.

### 7. Interactive Cyber Command Cockpit (Frontend UI)
- **Interactive Graph Canvas (Cytoscape.js + Dagre Layout)**: Hierarchical rendering with custom node styling (reported address, intermediary hops, mixer, exchange, bridge).
- **Animated SVG Flow Particles**: Dynamic token flow particles whose speed and stroke width reflect transaction volume and transfer velocity.
- **Interactive Timeline Scrubber**: Step backward and forward through time to watch illicit money laundering unfold step by step.
- **Drill-Down Inspector Rail & Drawer**: Deep examination of counterparties, cluster members, gas fees, block times, and direct block explorer hyperlinks.
- **Cyber Analytics Dashboard**: Aggregate incident metrics, typology distributions, top off-ramping exchanges, and live case monitoring.

---

## 🏗️ System Architecture

```mermaid
flowchart TB
    subgraph Client["Presentation Layer (Port 3000)"]
        UI["Next.js 15 Forensic Cockpit\n(React 19 / TypeScript / Tailwind)"]
        GraphViz["Cytoscape.js Canvas\n(Animated Particles + Dagre)"]
        Timeline["Timeline Scrubber\n(Temporal Playback)"]
        AnalyticsUI["Analytics & Reports Dashboard\n(Recharts / KPI Panels)"]
    end

    subgraph Gateway["API & Real-Time Gateway (Port 8000)"]
        FastAPI["FastAPI Orchestrator\n(Uvicorn / Pydantic v2)"]
        WS["WebSocket Streaming\n(/api/v1/trace/{id}/live)"]
        Router["V1 Router\n(/trace, /reports, /analytics)"]
    end

    subgraph Pipeline["Forensic Pipeline Engine"]
        Ingest["Multi-Chain Ingestor\n(BTC · ETH · TRON)"]
        ClusterEng["Clustering Heuristics\n(Multi-Input / Peeling / Reuse)"]
        BridgeEng["Cross-Chain Bridge Correlator\n(Time + Value Matching)"]
        TagMatcher["VASP & OFAC Sanctions Matcher\n(GraphSense / OFAC SDN)"]
        AgentEngine["Agentic LLM Reasoner\n(Groq Llama 3.3 70B / Rule Fallback)"]
        MLEngine["ML Risk Engine\n(XGBoost + TreeSHAP)"]
        ReportGen["PDF Dossier Engine\n(WeasyPrint + Jinja2 + BSA 2023 §63)"]
    end

    subgraph Storage["Persistence & Query Layer"]
        PG[("PostgreSQL 16\nSystem of Record\n(Raw TXs, Cases, Hash Chain)")]
        N4J[("Neo4j 5 Graph DB\nQuery & Traversal\n(Address & TX Subgraphs)")]
        RD[("Redis 7\nCache & Rate-Limit Gate")]
    end

    subgraph Blockchains["External Blockchain Data Providers"]
        ES["Etherscan V2 API (ETH / ERC-20)"]
        BC["Blockchair & Mempool.space (BTC)"]
        TG["TronGrid & Tronscan (TRON / TRC-20)"]
        OFAC["OFAC SDN Sanctions List"]
    end

    UI --> Router
    WS <--> UI
    Router --> FastAPI
    FastAPI --> Ingest
    Ingest --> RD
    Ingest --> Blockchains
    Ingest --> ClusterEng
    ClusterEng --> BridgeEng
    BridgeEng --> TagMatcher
    TagMatcher --> MLEngine
    MLEngine --> AgentEngine
    AgentEngine --> ReportGen
    
    Pipeline --> PG
    Pipeline --> N4J
    Router --> PG
    Router --> N4J
```

---

## 🔄 Forensic Pipeline Lifecycle

```mermaid
stateDiagram-v2
    [*] --> SUBMITTED : POST /api/v1/trace
    SUBMITTED --> INGESTING : Fetch On-Chain History (BTC/ETH/TRON)
    INGESTING --> CLUSTERING : Run Multi-Input & Peeling Heuristics
    CLUSTERING --> CORRELATING : Cross-Chain Bridge Correlation Window
    CORRELATING --> ATTRIBUTING : Match Curated Tags & OFAC Sanctions
    ATTRIBUTING --> SCORING : XGBoost Risk Classifier + SHAP Explainability
    SCORING --> NARRATING : Agentic AI Investigation Narrative
    NARRATING --> COMPLETED : Build Evidence Chain & Generate PDF
    
    INGESTING --> FAILED : API Rate Limit / Invalid Address
    CLUSTERING --> FAILED : Execution Error
    SCORING --> FAILED : Model Inference Failure
    FAILED --> [*]
    COMPLETED --> [*]
```

---

## 📊 Machine Learning Risk Scoring & Explainability

VajraTrace does not rely on opaque black-box scoring. It incorporates a calibrated **XGBoost Classifier** accompanied by **TreeSHAP** feature attributions.

### Training Dataset: Elliptic++
- Comprehensive benchmark containing over 200,000 Bitcoin transactions with ground-truth illicit/licit labels.
- Combines 166 local topological features (inflow/outflow volumes, fee ratios, transaction sizes) with 72 graph-level aggregation metrics (neighbor centrality, clustering coefficients, multi-hop variance).

### Performance Metrics (Holdout Evaluation)
```json
{
  "precision": 0.6882,
  "recall": 0.6038,
  "f1_score": 0.6432,
  "average_precision_score (PR-AUC)": 0.6768,
  "confusion_matrix": [
    [10374, 174],
    [252, 384]
  ]
}
```

### Top Feature Drivers (SHAP Importance)
| Feature Rank | Feature Name | Description | Impact on Risk Score |
| :---: | :--- | :--- | :--- |
| **#1** | `size` | Total inputs/outputs in the transaction | Increases risk for fan-out / peeling patterns |
| **#2** | `Local_feature_59` | Output value standard deviation | Distinguishes laundering spreads from normal sends |
| **#3** | `Aggregate_feature_32` | 2-hop aggregate transaction velocity | Captures rapid cross-wallet pass-throughs |
| **#4** | `Local_feature_53` | Input/Output volume ratio | Highlights mixing and peel-chain behavior |
| **#5** | `Local_feature_58` | Normalized transaction fee ratio | High fees indicate urgency to move illicit loot |

---

## 🤖 Agentic Investigation Reasoner

When an investigation is submitted, VajraTrace's AI Agent operates in a forensic loop mimicking an expert senior cyber investigator:

1. **`check_known_tags`**: Checks direct wallet addresses and parent clusters against curated exchange hot wallets, OTC brokers, mixers, and OFAC sanctions lists.
2. **`get_cluster`**: Expands target address into its co-controlled wallet cluster using multi-input and peeling heuristics.
3. **`check_bridge_correlation`**: Looks across blockchain networks for paired deposits/withdrawals matching transfer volume and timing.
4. **`get_risk_score`**: Invokes the XGBoost + SHAP pipeline to compute calibrated illicit probability.
5. **`synthesize_narrative`**: Synthesizes findings into plain-language paragraphs ready for judicial review.
6. **Graceful Degradation**: If Groq API keys are absent or network access is restricted, the built-in deterministic rule engine executes the identical sequence.

---

## ⚖️ Legal Admissibility & Court Compliance

Digital evidence in Indian courts must meet rigorous standards under the **Bharatiya Sakshya Adhiniyam (BSA), 2023**:

### Section 63 BSA 2023 (Admissibility of Electronic Records)
- VajraTrace maintains an **append-only, cryptographic hash-chain** stored in PostgreSQL.
- Every investigation step (`FETCH_TX_HISTORY`, `CLUSTER_ADDRESS`, `DETECT_BRIDGE_HOP`, `TAG_LOOKUP`, `RISK_SCORE`) generates a SHA-256 hash incorporating the previous step's hash:
  ```python
  payload = f"{step_number}|{action}|{result_summary or ''}|{prev_hash or ''}"
  integrity_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
  ```
- Any modification to database records breaks the cryptographic verification.
- The final PDF report contains an embedded SHA-256 hash of its entire binary content and a QR code pointing directly to the court verification endpoint.

### Statutory Freeze Orders (Section 91 / 102 BNSS)
- The platform automatically generates formatted notices under **Section 91 / 102 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023** (formerly Section 91/102 CrPC).
- Details suspect account addresses, deposit transaction hashes, recipient VASP identifiers, and immediate preservation directives.

---

## 🇮🇳 Proposed NCRP / I4C Integration Roadmap

```
+------------------+         +-------------------------------+
| Victim Complaint | ------> | NCRP Portal (cybercrime.gov.in)
+------------------+         +---------------+---------------+
                                             |
                                             v
                           +-----------------------------------+
                           | 1930 / CFCFRMS Incident Dispatch  |
                           +-----------------+-----------------+
                                             | (Crypto Suspect Wallet)
                                             v [Proposed Webhook]
                           +-----------------------------------+
                           | VajraTrace Ingest & Trace Engine  |
                           +-----------------+-----------------+
                                             |
            +--------------------------------+--------------------------------+
            |                                |                                |
            v                                v                                v
+-----------------------+        +-----------------------+        +-----------------------+
|  VASP Freeze Request  |        |  Samanvaya / Pratibimb|        | I4C Suspect Registry  |
|  (Binance, WazirX...) |        |  Inter-State Mapping  |        | Wallet Blacklisting   |
+-----------------------+        +-----------------------+        +-----------------------+
```

Detailed technical contracts, JSON schemas, webhook authentication, and data mapping specifications for the Indian Cybercrime Coordination Centre (I4C) are documented in [`docs/api-contract-ncrp.md`](docs/api-contract-ncrp.md).

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose / Justification |
| :--- | :--- | :--- |
| **Frontend Framework** | **Next.js 15 (App Router)** | Modern server/client hybrid rendering, SEO, edge routing |
| **UI Library** | **React 19 + TypeScript 5.6** | Robust typed interactive interface with concurrent rendering |
| **Graph Visualization** | **Cytoscape.js + Dagre** | Performant canvas-based rendering for 1,000+ nodes/edges |
| **State Management** | **Zustand 5** | Lightweight, reactive state management across graph & drawers |
| **Styling & Icons** | **Tailwind CSS + Lucide** | High-contrast dark cyber-forensic design system |
| **Backend Framework** | **FastAPI 0.115 (Python 3.11+)** | High-performance asynchronous API with OpenAPI docs |
| **Database (Relational)**| **PostgreSQL 16** | System of Record, `JSONB` cached responses, `NUMERIC(38,18)` |
| **Database (Graph)** | **Neo4j 5.x Community** | Native graph traversals, shortest path, cluster expansion |
| **Caching & Rate Limit**| **Redis 7** | Sub-millisecond API response caching and token buckets |
| **Machine Learning** | **XGBoost 2.0 + Scikit-Learn** | State-of-the-art gradient boosted decision tree classifier |
| **Explainable AI (XAI)**| **TreeSHAP 0.43** | Exact Shapley values providing feature-level transparency |
| **Agentic AI Reasoner**| **Groq (Llama 3.3 70B)** | High-speed LLM tool-calling with deterministic rule fallback |
| **PDF Generation** | **WeasyPrint 62 + Jinja2** | Pixel-perfect HTML-to-PDF engine with SHA-256 stamp & QR |
| **Containerization** | **Docker & Docker Compose** | Reproducible multi-service deployment across OS environments |

---

## 📁 Repository Structure

```
vajratrace/
├── .env.example                     # Environment configuration template
├── .gitignore                       # Git exclusion rules
├── docker-compose.yml               # Multi-container orchestration (API, Web, PG, Neo4j, Redis)
├── README.md                        # Master project documentation
│
├── apps/
│   ├── api/                         # FastAPI Backend Application
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/
│   │       ├── config.py            # Pydantic Settings & environment loader
│   │       ├── database.py          # SQLAlchemy (Postgres) & Neo4j driver connections
│   │       ├── main.py              # App entry point, CORS, extensions, startup hooks
│   │       ├── models.py            # PostgreSQL relational models (Cases, Evidence, Tags)
│   │       ├── schemas/             # Pydantic validation schemas
│   │       ├── api/v1/              # API Route Handlers
│   │       │   ├── router.py        # Aggregate v1 route bundle
│   │       │   └── endpoints/
│   │       │       ├── trace.py     # Multi-chain tracing & live WebSocket endpoint
│   │       │       ├── reports.py   # PDF report generator & download routes
│   │       │       └── analytics.py # Dashboard metrics & investigation registry
│   │       └── services/            # Core Forensic Engines
│   │           ├── agent/           # LLM Investigator Agent (Groq / Llama 3.3)
│   │           ├── attribution/     # VASP matching, confidence scoring, evidence logging
│   │           ├── blockchain/      # Multi-chain data fetchers (BTC, ETH, TRON)
│   │           ├── clustering/      # Multi-input & peeling chain heuristic engines
│   │           ├── ml/              # XGBoost inference, training, & typology classifier
│   │           └── reports/         # WeasyPrint PDF report engine & Jinja2 templates
│   │
│   └── web/                         # Next.js 15 Frontend Application
│       ├── Dockerfile
│       ├── package.json
│       ├── tailwind.config.ts
│       └── src/
│           ├── app/                 # Next.js App Router
│           │   ├── page.tsx         # Redirect to /trace
│           │   └── (dashboard)/     # Main Application Layout
│           │       ├── trace/       # Interactive Forensic Graph & Investigator Canvas
│           │       ├── analytics/   # Cyber Metrics & VASP Breakdown Dashboard
│           │       └── reports/     # Court Evidence Registry & PDF Downloader
│           ├── components/
│           │   ├── graph/           # Cytoscape Graph & Timeline Scrubber
│           │   ├── trace/           # Investigation Drawer, Left Rail, Risk Score Ring
│           │   └── ui/              # Button, Card, Sheet, Tooltip, Slider, Badge
│           ├── lib/                 # Typed API client, WebSocket client, utilities
│           └── stores/              # Zustand state stores (trace-store.ts)
│
├── data/
│   ├── models/                      # ML artifacts (risk_model.joblib, eval_report.json)
│   ├── ofac/                        # OFAC SDN Sanctions XML / Tag mappings
│   ├── reports/                     # Output directory for generated PDF dossiers
│   └── tags/                        # Curated VASP exchange hot wallet database
│
└── docs/
    ├── architecture.md              # Full 1,300+ line technical architecture specification
    └── api-contract-ncrp.md         # I4C / NCRP integration roadmap & technical schema
```

---

## 🚀 Quick Start Guide

### Option 1: Docker Compose (Recommended)

Ensure you have [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) installed.

```bash
# 1. Clone the repository
git clone https://github.com/atharva169/VajraTrace.git
cd VajraTrace

# 2. Configure environment
cp .env.example .env
# (Optional) Add your ETHERSCAN_API_KEY, TRONGRID_API_KEY, or GROQ_API_KEY to .env

# 3. Launch the full stack
docker compose up --build
```

Access the services in your browser:
- 🌐 **Forensic Web Dashboard:** [http://localhost:3000](http://localhost:3000)
- 📖 **Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- 🔍 **Neo4j Graph Browser:** [http://localhost:7474](http://localhost:7474) *(User: `neo4j` / Pass: `vajratrace`)*

---

### Option 2: Local Development Setup (Bare Metal)

#### 1. Prerequisites
- **Python:** `3.11` or higher
- **Node.js:** `18` or higher (`pnpm` or `npm`)
- **PostgreSQL 16**, **Neo4j 5**, and **Redis 7** running locally or via Docker.

```bash
# Run databases quickly via Docker
docker run -d --name vajra-pg -p 5432:5432 -e POSTGRES_USER=vajra -e POSTGRES_PASSWORD=vajra -e POSTGRES_DB=vajratrace postgres:16-alpine
docker run -d --name vajra-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/vajratrace neo4j:5
docker run -d --name vajra-redis -p 6379:6379 redis:7-alpine
```

#### 2. Backend Setup (FastAPI)
```bash
cd apps/api
python -m venv venv

# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt

# Start the API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 3. Frontend Setup (Next.js)
```bash
cd apps/web
npm install
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000).

---

## ⚙️ Configuration & Environment Variables

Create a `.env` file in the root directory based on `.env.example`:

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://vajra:vajra@localhost:5432/vajratrace` |
| `NEO4J_URI` | Bolt connection string for Neo4j | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j database username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j database password | `vajratrace` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `ETHERSCAN_API_KEY` | Etherscan V2 API key (for live ETH queries) | *Optional for offline/mock* |
| `TRONGRID_API_KEY` | TronGrid API key (for live TRON queries) | *Optional for offline/mock* |
| `GROQ_API_KEY` | Groq API Key for Llama 3.3 LLM agent | *Optional (defaults to rule fallback)* |
| `GROQ_MODEL` | Groq LLM model name | `llama-3.3-70b-versatile` |

---

## 📡 API Reference Overview

### Core Tracing Endpoints

#### `POST /api/v1/trace`
Submit a suspect blockchain wallet address for automated multi-chain forensic tracing.
```json
// Request Body
{
  "address": "0x71C8401367793a7317769e3B05E15f5aD3B3189A",
  "chain": "ETH",
  "depth": 3,
  "include_agent_narrative": true,
  "submitted_by": "Inspector Sharma (Cyber Cell)",
  "notes": "NCRP Ref: 2026/CYBER/88219"
}

// Response (202 Accepted)
{
  "trace_id": "8f3b2075-81d3-4674-bf83-8a07f311c1e5",
  "status": "SUBMITTED",
  "submitted_at": "2026-09-12T01:30:00Z",
  "ws_url": "/api/v1/trace/8f3b2075-81d3-4674-bf83-8a07f311c1e5/live"
}
```

#### `GET /api/v1/trace/{trace_id}`
Poll case status, high-level summary, attribution confidence, typology, and risk metrics.

#### `GET /api/v1/trace/{trace_id}/graph`
Fetch Cytoscape.js serialized subgraph (nodes, edges, transaction amounts, entity badges).

#### `GET /api/v1/trace/{trace_id}/evidence`
Retrieve the cryptographically chained audit trail for Section 63 BSA compliance.
```json
{
  "trace_id": "8f3b2075-81d3-4674-bf83-8a07f311c1e5",
  "integrity_valid": true,
  "steps": [
    {
      "step_number": 0,
      "action": "FETCH_TX_HISTORY",
      "description": "Fetched on-chain transactions for 0x71C8... on Ethereum",
      "prev_hash": null,
      "integrity_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  ]
}
```

#### `WS /api/v1/trace/{trace_id}/live`
Live bidirectional WebSocket stream delivering sub-second pipeline milestone notifications:
- `status_change`
- `tx_discovered`
- `cluster_formed`
- `bridge_hop`
- `tag_match`
- `sanctions_alert`
- `agent_message`
- `completed`

---

### Reports & Analytics Endpoints

#### `POST /api/v1/reports/{trace_id}/pdf`
Asynchronously generates a court-admissible PDF investigation dossier.

#### `GET /api/v1/reports/{trace_id}/download`
Download the generated PDF evidence dossier with embedded digital hash and freeze notice.

#### `GET /api/v1/analytics/overview`
Aggregated dashboard KPIs: total traces, attribution success rate, sanctions hits, top off-ramping VASPs, typology frequencies, and chain distributions.

#### `GET /api/v1/analytics/recent`
Paginated search and filter registry of active and completed investigations.

---

## 🧪 Testing & Verification

```bash
# Verify API Health
curl http://localhost:8000/health

# Trigger Test Investigation Trace
curl -X POST http://localhost:8000/api/v1/trace \
  -H "Content-Type: application/json" \
  -d '{"address": "0x71C8401367793a7317769e3B05E15f5aD3B3189A", "chain": "ETH"}'

# Verify Evidence Integrity Chain
curl http://localhost:8000/api/v1/trace/<trace_id>/evidence?verify_integrity=true
```

---

## 🗺️ Future Roadmap

- [ ] **Expanded Blockchain Support**: Integration of high-frequency consumer chains (**Solana**, **Polygon PoS**, **Arbitrum One**, **TRON SUN Network**).
- [ ] **Graph Neural Networks (GNNs)**: Deploying relational GCN/GAT models on Neo4j for topological node classification.
- [ ] **Gov-Cloud Integration**: Native deployment blueprints for **NIC Cloud (MeghRaj)** and State Data Centres (SDCs).
- [ ] **Single Sign-On (SSO)**: National authentication integration via **Jan Parichay** / **e-Pramaan** for law enforcement verification.
- [ ] **Automated FIU-IND Reporting**: Direct export to Suspicious Transaction Report (STR) XML format for FIU compliance desks.

---

## 👥 Team Servidor — Smart India Hackathon 2026

*Dedicated to strengthening India's cybersecurity posture, accelerating victim asset recovery, and building sovereign, world-class law enforcement technology.*

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
