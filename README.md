<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/scikit--learn-1.3-F7931E?logo=scikit-learn&logoColor=white" alt="scikit-learn">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

# SentinelAI

**AI-Powered Network Security Alert Triage System**

SentinelAI is an intelligent network intrusion detection and alert triage platform that combines a Random Forest classifier with a calibrated two-stage decision engine to automatically classify, prioritize, and triage network security alerts in real time.

---

## Overview

Security Operations Centers (SOCs) face overwhelming volumes of network alerts daily. SentinelAI addresses alert fatigue by automating the triage process with a machine learning pipeline that classifies network flows into 10 attack categories, assigns priority levels, and recommends analyst actions — all with SHAP-powered explainability.

### Key Capabilities

- **10-Class Attack Detection** — Classifies network traffic as Benign or one of 9 attack types (DDoS, PortScan, Brute Force, Web Attack, Bot, Infiltration, Heartbleed, FTP-Patator, SSH-Patator)
- **Calibrated Two-Stage Triage** — Dual-threshold policy (THETA_LOW=0.20, THETA_HIGH=0.70) assigns alerts to four priority bands: Low, Medium, High, Critical
- **Real-Time Live Capture** — WebSocket-based packet capture with CICFlowMeter feature extraction and instant classification
- **Batch Analysis** — Upload PCAP or CSV files for bulk flow analysis
- **SHAP Explanations** — Feature-level attribution for every prediction, showing analysts *why* an alert was raised
- **Unified SOC Dashboard** — Consolidated view with priority distribution, attack breakdown, trend analysis, and filterable alert table
- **PDF Report Export** — One-click executive summary reports with priority breakdown and top threats
- **Alert Status Tracking** — Full lifecycle workflow: New → Acknowledged → Investigating → Resolved / False Positive
- **Alert Correlation & Grouping** — Automatic clustering of related alerts by attack class within 5-minute time windows
- **Laya NLP Interface** — Natural language chat for querying alerts and getting plain-English explanations (advisory only — the LLM never controls security decisions)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                        │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌───────────┐ │
│  │ Dashboard │ │LiveCapture│ │BatchUpload│ │  ChatView │ │
│  └────┬─────┘ └─────┬─────┘ └────┬─────┘ └─────┬─────┘ │
│       └──────────────┼───────────┘              │       │
│              AlertStatsContext                   │       │
└──────────────────────┬──────────────────────────┘       │
                       │ REST + WebSocket                  │
┌──────────────────────┴──────────────────────────────────┐
│                   FastAPI Backend                        │
│  ┌────────────┐ ┌────────────────┐ ┌──────────────────┐ │
│  │  API Layer │ │ Decision Engine│ │  SHAP Explainer  │ │
│  └──────┬─────┘ └───────┬────────┘ └────────┬─────────┘ │
│         │               │                    │           │
│  ┌──────┴─────┐ ┌───────┴────────┐ ┌────────┴─────────┐│
│  │  Storage   │ │ RF Classifier  │ │  Live Capture    ││
│  │  (SQLite)  │ │   (C7 Model)   │ │    Engine        ││
│  └────────────┘ └────────────────┘ └──────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
SentinelAI/
├── frontend/                    # React + TypeScript + Vite
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.tsx        # Unified SOC dashboard
│   │   │   ├── LiveCapture.tsx      # Real-time packet capture UI
│   │   │   ├── BatchUpload.tsx      # Batch file analysis
│   │   │   ├── ChatView.tsx         # Laya NLP interface
│   │   │   ├── TriageView.tsx       # Manual triage view
│   │   │   ├── AlertStatsContext.tsx # Shared alert state provider
│   │   │   ├── Sidebar.tsx          # Navigation sidebar
│   │   │   └── ...
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css                # SOC-themed dark design system
│   ├── package.json
│   └── vite.config.ts
│
├── src/sentinelai/              # Python backend package
│   ├── api.py                       # FastAPI routes & endpoints
│   ├── batch.py                     # Batch processing pipeline
│   ├── model.py                     # Model loading & inference
│   ├── shap_explanations.py         # SHAP feature attribution
│   ├── laya_client.py               # LLM integration (advisory only)
│   ├── capture/                     # Live capture engine
│   │   ├── engine.py                    # Packet capture orchestrator
│   │   ├── feature_extractor.py         # CICFlowMeter feature extraction
│   │   ├── flow_table.py               # Flow tracking & aggregation
│   │   ├── flow_state.py               # Flow state management
│   │   ├── live_session.py             # WebSocket session handler
│   │   └── api_routes.py              # Capture-specific routes
│   ├── storage/
│   │   └── db.py                    # SQLite persistence layer
│   └── triage/
│       ├── decision_engine.py       # Two-stage triage policy
│       └── calibrated_params_fresh.json
│
├── scripts/                     # Training & evaluation
│   ├── train_fresh_model.py
│   ├── evaluate_fresh_pipeline.py
│   ├── calibrate_fresh_policy.py
│   ├── validate_model.py
│   ├── benchmark_c7.py
│   └── ...
│
├── tests/                       # Test suite (27 test files)
│   ├── test_api_alerts.py
│   ├── test_calibrated_policy.py
│   ├── test_triage_decision.py
│   ├── test_batch.py
│   ├── test_storage.py
│   └── ...
│
├── models/                      # Trained model artifacts
├── requirements.txt
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm or yarn

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/HarithaRavichandar/SentinelAI.git
cd SentinelAI

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\Activate.ps1    # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Start the backend server
uvicorn sentinelai.api:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will be available at `http://localhost:5173` and proxies API requests to the backend at `http://localhost:8000`.

---

## Usage

### Live Capture

Navigate to the **Live Capture** view to monitor network traffic in real time. The system captures packets, extracts CICFlowMeter features, classifies flows through the C7 model, and streams results to the dashboard via WebSocket with automatic reconnection.

### Batch Analysis

Upload a PCAP or CSV file through the **Batch Upload** view for bulk analysis. Results are processed through the same classification and triage pipeline, then populated into the unified dashboard.

### Dashboard

The **Dashboard** aggregates alerts from all sources (triage, live capture, batch upload) and provides:

- Priority distribution bar chart
- Attack class breakdown pie chart
- Alert trend line chart over time
- Filterable and sortable alert table with inline status management
- Correlated incident groups (alerts clustered by attack type within 5-minute windows)
- CSV export and PDF report generation

### Alert Lifecycle

Track each alert through its lifecycle using the status dropdown in the alert table:

| Status | Description |
|--------|-------------|
| `New` | Freshly detected, awaiting analyst review |
| `Acknowledged` | Analyst has seen the alert |
| `Investigating` | Active investigation in progress |
| `Resolved` | Confirmed threat, remediated |
| `False Positive` | Determined to be benign |

---

## Model Details

| Property | Value |
|----------|-------|
| Algorithm | Random Forest (scikit-learn 1.3.2) |
| Classes | 10 (Benign + 9 attack types) |
| Features | 76 CICFlowMeter network flow features |
| Training Data | CIC-IDS2017 dataset |
| Triage Policy | Two-stage calibrated thresholds |
| Explainability | SHAP TreeExplainer |

### Triage Thresholds

```
p_attack < 0.20  →  LOW priority      →  Auto-close
0.20 ≤ p < 0.70  →  MEDIUM priority   →  Queue for review
0.70 ≤ p < 0.90  →  HIGH priority     →  Escalate
p_attack ≥ 0.90  →  CRITICAL priority →  Immediate response
```

> **Design principle:** The LLM component (Laya) provides natural language explanations only. All security classification and triage decisions are made exclusively by the calibrated ML pipeline — the LLM never controls security-critical actions.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/triage` | Classify a single flow |
| `POST` | `/api/batch` | Submit batch analysis job |
| `GET` | `/api/batch/{job_id}` | Poll batch job status |
| `GET` | `/api/alerts` | Retrieve stored alerts |
| `PATCH` | `/api/alerts/{id}/status` | Update alert status |
| `POST` | `/api/shap` | Get SHAP explanations |
| `GET` | `/api/health` | Backend health check |
| `WS` | `/ws/capture` | Live capture WebSocket |

---

## Testing

```bash
# Run the full test suite
pytest

# Run with verbose output
pytest -v

# Run specific test module
pytest tests/test_calibrated_policy.py
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Recharts |
| Backend | FastAPI, Uvicorn, Python 3.11 |
| ML/AI | scikit-learn, SHAP, Random Forest |
| Database | SQLite |
| Live Capture | WebSocket, CICFlowMeter |
| NLP | Laya (LLM-based, advisory only) |

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'feat: add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [CIC-IDS2017 Dataset](https://www.unb.ca/cic/datasets/ids-2017.html) — Canadian Institute for Cybersecurity
- [CICFlowMeter](https://github.com/ahlashkari/CICFlowMeter) — Network flow feature extraction
- [SHAP](https://github.com/shap/shap) — SHapley Additive exPlanations for model interpretability
