<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white" alt="scikit-learn">
</p>

<h1 align="center">SentinelAI</h1>

<p align="center">
  <strong>AI-Powered Network Security Alert Triage System</strong><br>
  <em>Automated classification, prioritization, and triage of network intrusion alerts — built for Security Operations Centers.</em>
</p>

<p align="center">
  <a href="#-features">Features</a> · <a href="#-how-it-works">How It Works</a> · <a href="#-getting-started">Getting Started</a> · <a href="#-tech-stack">Tech Stack</a> · <a href="#-contributing">Contributing</a>
</p>

---

## The Problem

Security Operations Centers deal with **thousands of network alerts daily**. The vast majority are false positives, but buried in the noise are real threats that demand immediate attention. Analysts experience alert fatigue — critical incidents get missed, response times increase, and threats slip through.

## The Solution

SentinelAI automates the triage pipeline. A trained Random Forest classifier analyzes network traffic flows, identifies attack patterns across 10 categories, and assigns each alert a calibrated priority level — so analysts focus on what matters instead of drowning in noise.

Every decision is explainable. SHAP-powered feature attribution shows analysts *why* each alert was flagged, building trust in the automation and enabling faster investigation.

<p align="center">
  <img src="data/screenshots/Dashboard Overview.jpeg" alt="SentinelAI Dashboard" width="90%">
  <br><em>Unified SOC Dashboard — real-time KPIs, classification breakdown, and source distribution</em>
</p>

---

##  Features

### Real-Time Live Capture
Monitor network traffic as it happens. SentinelAI captures packets, extracts 76 CICFlowMeter features from each flow, runs classification through the trained model, and streams results to the dashboard — all via WebSocket with automatic reconnection and exponential backoff. Alerts appear on the dashboard the moment they're detected.

<p align="center">
  <img src="data/screenshots/Live Capture.jpeg" alt="Live Capture" width="90%">
  <br><em>Real-time packet classification with priority-colored rows and flow details</em>
</p>

### Batch Analysis
Upload PCAP or CSV files for bulk analysis of historical traffic. The batch pipeline processes every flow through the same classification and triage engine, then feeds results into the unified dashboard alongside live alerts. Useful for incident investigation, threat hunting, or auditing captured traffic.

### Unified SOC Dashboard
A consolidated command center that aggregates alerts from every source — manual triage, live capture, and batch uploads — into a single view.

<p align="center">
  <img src="data/screenshots/Dashboard Analytics.jpeg" alt="Dashboard Analytics" width="90%">
  <br><em>Threat distribution, activity timeline, and correlated incident groups</em>
</p>

The dashboard includes:

- **Priority distribution** — Bar chart showing alert volume across Low, Medium, High, and Critical bands
- **Attack class breakdown** — Pie chart of detected attack types (DDoS, PortScan, Brute Force, Web Attack, Bot, etc.)
- **Alert trend timeline** — Line chart tracking alert volume over time to spot surges
- **Filterable alert table** — Sort by priority, attack type, source, or status; manage alerts inline
- **CSV export** — Download the full alert dataset for external analysis

### Alert Status Tracking
Track every alert through its full lifecycle with an inline status dropdown directly in the alert table:

<p align="center">
  <img src="data/screenshots/Alert History.jpeg" alt="Alert History" width="90%">
  <br><em>Persistent alert table with priority badges, source tags, filters, and CSV/PDF export</em>
</p>

**New** → **Acknowledged** → **Investigating** → **Resolved** or **False Positive**

Status changes persist to the SQLite backend, so alert state survives page refreshes and is shared across sessions. Analysts can filter the dashboard by status to focus on open investigations or review resolved incidents.

### Alert Correlation & Grouping
SentinelAI automatically clusters related alerts into incident groups. The correlation engine identifies alerts sharing the same attack classification within 5-minute time windows and groups them together. Instead of investigating 50 individual DDoS alerts, an analyst sees one correlated incident with a count, time range, and expandable detail view. This dramatically reduces investigation time for coordinated or sustained attacks.

### PDF Report Export
Generate executive-ready incident reports with one click. The PDF export produces a formatted summary including:

- Executive overview with total alert count and time range
- Priority breakdown with percentages
- Source distribution (live capture vs. batch vs. manual triage)
- Top threat types ranked by frequency
- Table of critical alerts with timestamps and details

Opens in a new browser tab for immediate Print or Save as PDF.

### SHAP Explainability
Every prediction comes with feature-level attribution powered by SHAP TreeExplainer. Analysts can see exactly which network flow characteristics (packet size, flow duration, flag counts, etc.) contributed most to the classification. This transparency is essential for SOC workflows — analysts need to understand *why* an alert was raised before they can act on it.

### Laya — Natural Language Assistant
Ask questions about alerts in plain English. Laya is an LLM-powered conversational interface (backed by Groq or Gemini) that can explain predictions, summarize alert patterns, and answer security-related queries. 

<p align="center">
  <img src="data/screenshots/Laya Chat.jpeg" alt="Laya Chat" width="90%">
  <br><em>Laya provides structured triage guidance for DoS alert investigation</em>
</p>

> **Safety by design:** Laya is strictly advisory. All classification and triage decisions are made exclusively by the calibrated ML pipeline — the LLM never controls security-critical actions.

---

##  How It Works

### Classification Pipeline
The core model is a **Random Forest classifier** trained on the [UNSW-NB15 dataset](https://research.unsw.edu.au/projects/unsw-nb15-dataset) with **76 network flow features**. It classifies traffic into 10 categories:

| Class | Description |
|-------|-------------|
| Benign | Normal traffic |
| Analysis | Port scan, spam, HTML vulnerability probes |
| Backdoor | Covert unauthorized remote access |
| DoS | Denial of Service flooding |
| Exploits | Known vulnerability exploitation |
| Fuzzers | Protocol and input fuzzing attacks |
| Generic | Generic attack signatures |
| Reconnaissance | Network mapping and information gathering |
| Shellcode | Remote code execution payloads |
| Worms | Self-propagating malware |

### Two-Stage Triage Policy
Raw model output passes through a calibrated decision engine with dual thresholds, assigning alerts to four priority bands:

```
   p_attack < 0.20   →   🟢 LOW        Auto-close
0.20 ≤ p_attack < 0.70   →   🟡 MEDIUM     Queue for review
0.70 ≤ p_attack < 0.90   →   🟠 HIGH       Escalate
   p_attack ≥ 0.90   →   🔴 CRITICAL   Immediate response
```

Thresholds (θ_low = 0.20, θ_high = 0.70) are calibrated on a held-out validation set — not tuned on the test partition — ensuring honest generalization estimates.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      React Frontend                          │
│                                                              │
│   Dashboard  ·  LiveCapture  ·  BatchUpload  ·  ChatView    │
│         └──────────┬───────────────┘                         │
│            AlertStatsContext (shared state)                   │
└────────────────────┬────────────────────────────────────────┘
                     │  REST + WebSocket
┌────────────────────┴────────────────────────────────────────┐
│                      FastAPI Backend                          │
│                                                              │
│   Inference Engine  →  Decision Engine  →  SHAP Explainer    │
│         │                    │                                │
│   Live Capture Engine    SQLite Storage    LLM Client (Laya) │
└──────────────────────────────────────────────────────────────┘
```

---

##  Getting Started

### Prerequisites

- **Python 3.11+** with pip
- **Node.js 18+** with npm

### 1. Clone & Install

```bash
git clone https://github.com/HarithaRavichandar/SentinelAI.git
cd SentinelAI
```

### 2. Backend

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\Activate.ps1      # Windows PowerShell

# Install dependencies
pip install -r requirements.txt

# Configure environment (optional — see .env.example)
cp .env.example .env

# Start the server
uvicorn sentinelai.api:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** — the frontend proxies API requests to the backend automatically.

### 4. (Optional) LLM for Laya

To enable the natural language assistant, set your API key in `.env`:

```env
# Groq (default)
LLM_PROVIDER=groq
GROQ_API_KEY=your_key_here

# Or Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

Laya falls back to deterministic template explanations if no API key is configured.

---

##  Testing

```bash
# Full suite
pytest

# Verbose
pytest -v

# Specific module
pytest tests/test_calibrated_policy.py -v
```

The test suite covers the inference engine, triage decision logic, API endpoints, SHAP explanations, alert storage, batch processing, and LLM client behavior.

---

##  Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | React 18, TypeScript, Vite, Recharts, CSS (custom SOC dark theme) |
| **Backend** | FastAPI, Uvicorn, Python 3.11, SQLite |
| **ML Pipeline** | scikit-learn 1.3, SHAP TreeExplainer, Random Forest |
| **Live Capture** | WebSocket, CICFlowMeter feature extraction |
| **NLP** | Groq or Google Gemini — configurable LLM provider, advisory only |

---

##  Project Structure

```
SentinelAI/
├── frontend/src/
│   ├── components/
│   │   ├── Dashboard.tsx           # Unified SOC dashboard with charts, filters, export
│   │   ├── LiveCapture.tsx         # Real-time network capture interface
│   │   ├── BatchUpload.tsx         # Bulk file analysis
│   │   ├── ChatView.tsx            # Laya natural language assistant
│   │   ├── AlertStatsContext.tsx    # Shared alert state across all views
│   │   ├── TriageView.tsx          # Manual single-flow triage
│   │   └── Sidebar.tsx             # Navigation
│   ├── api.ts                      # Backend API client
│   └── index.css                   # SOC-themed dark design system
│
├── src/sentinelai/
│   ├── api.py                      # FastAPI application & routes
│   ├── inference.py                # Model loading & prediction
│   ├── batch.py                    # Batch processing pipeline
│   ├── capture/                    # Live packet capture engine
│   ├── storage/db.py               # SQLite alert persistence
│   ├── triage/
│   │   ├── decision_engine.py      # Two-stage calibrated triage
│   │   ├── llm_client.py           # LLM provider facade (Groq/Gemini)
│   │   └── prompt_builder.py       # Explanation prompt templates
│   ├── features/preprocessing.py   # Feature scaling & validation
│   └── models/random_forest.py     # Random Forest model wrapper
│
├── scripts/                        # Training, evaluation & calibration
├── tests/                          # 20+ test modules
├── .env.example                    # Environment configuration template
└── requirements.txt
```

---

##  Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push and open a Pull Request

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Acknowledgments

- [CIC-IDS2017 Dataset](https://www.unb.ca/cic/datasets/ids-2017.html) — Canadian Institute for Cybersecurity
- [CICFlowMeter](https://github.com/ahlashkari/CICFlowMeter) — Network flow feature extraction
- [SHAP](https://github.com/shap/shap) — SHapley Additive exPlanations for model interpretability
