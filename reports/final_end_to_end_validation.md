# SentinelAI Final End-to-End Regression and Demo Readiness Audit

**Audit Date:** November 11, 2026  
**Auditor:** Automated Regression & Verification Harness (Antigravity)  
**Target Codebase:** SentinelAI (`H:\SentinelAI`)  
**Scope:** Final End-to-End Validation across ML Inference, Two-Stage Decision Engine, Laya AI Provenance, Documentation, and Frontend Architecture (Tasks 1–5 Verification)  
**Overall Verdict:** **PASS WITH WARNINGS**

---

## Executive Summary

A comprehensive, end-to-end regression audit was conducted on SentinelAI to verify production readiness, backward compatibility, and demo reliability. All functional test suites, runtime endpoints, model/policy combinations, and build pipelines passed without regression. 

The verdict **PASS WITH WARNINGS** reflects full operational readiness, with warnings strictly confined to:
1. Third-party library deprecation notices (`StarletteTestClient` deprecating `httpx`, and SHAP `TreeExplainer` deprecating `feature_perturbation='interventional'` without an explicit background dataset).
2. Documented validation-stage policy characteristics (the 1.292% Benign False Positive Rate under the experimental two-stage policy, and the unvalidated pairing warning when running legacy models with the fresh two-stage policy).

Zero modifications were made to frozen model weights, evaluation split masks, calibration parameters, or baseline metrics during this audit.

---

## 1. Preflight Configuration Audit

The project configuration was inspected across environment variables, fallback mechanisms, configuration templates, and runtime dependencies:

| Configuration Item | Expected Standard | Observed Implementation | Status |
| :--- | :--- | :--- | :---: |
| `SENTINELAI_MODEL_VERSION` | Defaults to `legacy` | Evaluates to `"legacy"` when unset in `InferenceEngine.__init__` | **PASS** |
| `SENTINELAI_TWO_STAGE_TRIAGE` | Defaults to `false` | Evaluates to `False` when unset in `evaluate_triage_decision` | **PASS** |
| Fresh Model Isolation | Loads only fresh model & preprocessor | Correctly targets `data/models_fresh/random_forest_fresh.pkl` and `preprocessor_fresh.pkl` | **PASS** |
| Invalid Model Handling | Immediate fail-fast | Raises `ModelConfigurationError` with supported choices listed | **PASS** |
| Calibrated Policy Flag | Only loads on `true` | Loads frozen `calibrated_params_fresh.json` only when flag enabled | **PASS** |
| Legacy Policy Parity | Unmodified when flag is `false` | Preserves hardcoded class reliability, thresholds, and routing | **PASS** |
| Laya Advisory Boundary | Advisory-only NLP layer | Decisions and ML classifications execute independently of Laya | **PASS** |
| Laya Fallback Handling | Graceful template fallback | Missing API keys trigger `placeholder.py` without triage failure | **PASS** |
| Explanation Provenance | Transparent source tracking | Response returns `explanation_source` and `explanation_provenance` | **PASS** |
| `.env.example` Integrity | Honest defaults documented | Lists all supported env vars including `SENTINELAI_DB_PATH=data/alerts.db` | **PASS** |
| `requirements.txt` | Complete dependency list | Matches active Python 3.11 virtual environment requirements | **PASS** |

---

## 2. Backend Test Suite Execution

The entire backend test suite was executed via pytest using Python 3.11:

```powershell
.\.venv\Scripts\pytest.exe -o pythonpath=. tests\ -v
```

### Test Execution Summary

- **Total Tests Collected:** 141
- **Passed:** 141 (100%)
- **Failed:** 0
- **Skipped:** 0
- **Total Duration:** 299.28 seconds (~4 minutes 59 seconds)
- **Warnings:** 28

### Warnings Breakdown

1. **Starlette Deprecation Warning (25 occurrences):**  
   `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`  
   *Assessment:* Non-fatal testing harness warning from upstream FastAPI/Starlette test client. Does not affect production ASGI server execution (`uvicorn`).
2. **SHAP TreeExplainer Future Warning (2 occurrences):**  
   `FutureWarning: In the future, passing feature_perturbation='interventional' without providing a background dataset will raise an error.`  
   *Assessment:* Pre-warming and per-sample tree explanations compute cleanly; warning concerns future SHAP releases.
3. **Scikit-Learn Metric Warning (1 occurrence):**  
   `UndefinedMetricWarning: Precision is ill-defined and being set to 0.0 in labels with no predicted samples.`  
   *Assessment:* Occurs in synthetic test case (`tests/test_model_validation.py`) where certain classes have 0 predicted samples in edge evaluation.

---

## 3. Runtime Endpoint Smoke-Test Results

All core backend HTTP endpoints were tested against the running API application:

| Endpoint | Method | Query / Payload | Expected Response | Observed Response | Status |
| :--- | :---: | :--- | :--- | :--- | :---: |
| `/health` | GET | None | `{"status": "ok"}` | `{"status": "ok"}` (200 OK) | **PASS** |
| `/health` | GET | `?model_info=true` | `{"status": "ok", "model_version": "legacy"}` | `{"status": "ok", "model_version": "legacy"}` (200 OK) | **PASS** |
| `/status` | GET | None | System status, active model version, path, feature count | `{"status": "ok", "model_version": "legacy", "model_path": "...balanced.pkl", "columns_count": 76}` (200 OK) | **PASS** |
| `/sample` | GET | None | Synthetic/representative 76 numerical features | Returns 76 finite numerical floats (200 OK) | **PASS** |
| `/sample` | GET | `?label=Benign` | 76 numerical features matching Benign class | Returns 76 finite numerical floats, `label: "Benign"` (200 OK) | **PASS** |
| `/sample` | GET | `?label=Exploits` | 76 numerical features matching Exploits class | Returns 76 finite numerical floats, `label: "Exploits"` (200 OK) | **PASS** |
| `/alerts` | GET | `?limit=10` | JSON list of alerts with decision, provenance, and SHAP | Returns array of recent alerts adhering to schema (200 OK) | **PASS** |

---

## 4. Model and Policy Configuration Matrix

All four valid runtime combinations of `SENTINELAI_MODEL_VERSION` and `SENTINELAI_TWO_STAGE_TRIAGE`, plus invalid configuration rejection, were empirically validated:

| Matrix Case | `MODEL_VERSION` | `TWO_STAGE` | Observed Engine State | Policy Mode Applied | Decision Behavior & Warnings | Status |
| :---: | :---: | :---: | :--- | :--- | :--- | :---: |
| **1** | `legacy` | `false` | `random_forest_balanced.pkl` | `legacy` | Standard threshold routing; low priority on benign; no operational warnings. | **PASS** |
| **2** | `legacy` | `true` | `random_forest_balanced.pkl` | `two_stage_experimental` | Loads fresh calibrated params; attaches explicit warning to `evidence` and `uncertainty_reasons`: *"Operational warning: Experimental two-stage policy was calibrated on fresh validation data; operating with legacy model lacks matching validation guarantees."* | **PASS** |
| **3** | `fresh` | `false` | `random_forest_fresh.pkl` | `legacy` | Fresh model features evaluated under baseline legacy decision engine. | **PASS** |
| **4** | `fresh` | `true` | `random_forest_fresh.pkl` | `two_stage_experimental` | Fully validated pairing; two-stage triage executed with frozen validation calibration (`calibrated_params_fresh.json`). | **PASS** |
| **Error** | `invalid_v99` | `false` | Fail-fast initialization | N/A | Immediately raises `ModelConfigurationError("Unsupported SENTINELAI_MODEL_VERSION 'invalid_v99'...")`. | **PASS** |

---

## 5. End-to-End Triage Workflow Results

Genuine multi-class dataset samples (76 numerical network traffic features) were ingested through `/triage?explain_shap=true` to test the full pipeline:

### Real-Sample Test Results

```
================================================================================
END-TO-END TRIAGE REAL SAMPLE EVALUATION
================================================================================

1. Category: Benign (Sample ID: 154)
   - Predicted Class: Benign (Class ID: 0)
   - Top Class Probability: 1.0000 (100.0%)
   - Decision Priority: low
   - Decision Status: accepted
   - Recommended Action: allow_and_standard_monitoring
   - Decision Confidence: 0.995
   - Requires Human Review: False
   - Explanation Source: groq
   - Provenance: Generated by Groq (is_llm: True)
   - SHAP Feature Explanations: 76 features computed
   - Database Persistence: Successfully persisted in data/alerts.db

2. Category: Exploits (Sample ID: 155)
   - Predicted Class: Exploits (Class ID: 4)
   - Top Class Probability: 0.9800 (98.0%)
   - Decision Priority: critical
   - Decision Status: accepted
   - Recommended Action: isolate_workstation_and_open_incident
   - Decision Confidence: 0.915
   - Requires Human Review: True
   - Explanation Source: groq
   - Provenance: Generated by Groq (is_llm: True)
   - SHAP Feature Explanations: 76 features computed
   - Database Persistence: Successfully persisted in data/alerts.db

3. Category: Shellcode (Sample ID: 156) [Minority Attack Class]
   - Predicted Class: Shellcode (Class ID: 8)
   - Top Class Probability: 0.7250 (72.5%)
   - Decision Priority: high
   - Decision Status: review_required
   - Recommended Action: manual_deep_packet_inspection
   - Decision Confidence: 0.492
   - Requires Human Review: True
   - Explanation Source: groq
   - Provenance: Generated by Groq (is_llm: True)
   - SHAP Feature Explanations: 76 features computed
   - Database Persistence: Successfully persisted in data/alerts.db
```

---

## 6. Laya Provider & Provenance Fallback Validation

The Laya natural-language explanation layer was tested under both live and disconnected conditions:

1. **Live Provider Execution (`groq`):**
   - Live Groq API calls succeeded with HTTP 200 OK.
   - Natural language explanations correctly synthesized model predictions, class probabilities, and top SHAP features.
   - Metadata returned: `explanation_source: "groq"`, `explanation_provenance: {"source": "groq", "is_llm": true, "provider": "groq", "label": "Generated by Groq"}`.
2. **Disconnected Fallback Execution (`template`):**
   - When API credentials (`GROQ_API_KEY` / `GEMINI_API_KEY`) were cleared or unreachable, the system gracefully intercepted `LLMConfigurationError`.
   - Dynamic explanation was replaced with deterministic output from `placeholder.py`: `"[Placeholder] Unable to generate explanation for class 'Benign'..."`.
   - Metadata returned: `explanation_source: "template"`, `explanation_provenance: {"source": "template", "is_llm": false, "provider": null, "label": "Template explanation"}`.
   - Triage classification, decision scoring, and SQLite persistence completed without raising HTTP 500 errors.
3. **Advisory Non-Interference:**
   - Classification outputs, routing priority (`low` vs `high` vs `critical`), and remediation recommendations remained 100% deterministic and unaffected by Laya response content.

---

## 7. Frontend Build and Navigation Audit

The frontend application (`frontend/`) was audited for compilation integrity and navigation honesty:

### Build Pipeline

- **Build Command:** `npm --prefix frontend run build`
- **Modules Transformed:** 890 modules
- **Build Output:** `dist/index.html` (0.38 kB), `dist/assets/index-*.css` (6.63 kB), `dist/assets/index-*.js` (759.98 kB)
- **Build Result:** Success (0 errors, 12.92 seconds)

### Navigation & Route Audit

Inspection of `frontend/src/App.tsx` and `frontend/src/components/Sidebar.tsx` confirms that the user interface is cleanly focused on the three fully implemented views:

| View | Route Defined in `App.tsx` | Present in `Sidebar.tsx` | Status | Implementation Details |
| :--- | :---: | :---: | :---: | :--- |
| **Dashboard** | `/` | Yes (`navItems`) | **Fully Functional** | Primary view containing KPI metric cards, alert status distributions, system health status, search and filtering controls, CSV export, and the integrated Alert History & Triage Records audit log. |
| **Alert Triage** | `/triage` | Yes (`navItems`) | **Fully Functional** | Interactive analyst workspace with sample loader, raw payload editor, real-time SHAP feature breakdown, and transparent Laya AI provenance badges. |
| **Laya Chat** | `/chat` | Yes (`navItems`) | **Fully Functional** | Advisory multi-turn conversational interface with provider badge, markdown rendering, and strict security guardrails. |
| **Alert History** | Integrated in `/` | No (in-page) | **Fully Functional** | Implemented directly within `Dashboard.tsx` (`Alert History & Triage Records` table with search, priority/class filters, and CSV export). No standalone `/history` route exists. |
| **Reports** | None | No | **Placeholder Excluded** | Component `Reports.tsx` is an unfinished placeholder. Excluded from `Sidebar.tsx` and `App.tsx` routes to prevent dead placeholder clicks. |
| **Settings** | None | No | **Placeholder Excluded** | Component `Settings.tsx` is an unfinished placeholder. Excluded from `Sidebar.tsx` and `App.tsx` routes to prevent dead placeholder clicks. |
| **Analysis** | None | No | **Placeholder Excluded** | Component `Analysis.tsx` is an unfinished placeholder. Excluded from `Sidebar.tsx` and `App.tsx` routes. |
| **Traffic Monitor** | None | No | **Placeholder Excluded** | Component `TrafficMonitor.tsx` is an unfinished placeholder. Excluded from `Sidebar.tsx` and `App.tsx` routes. |

### Unknown Route & Placeholder Fallback Behavior

In `frontend/src/App.tsx`, the routing table is defined as:

```tsx
<Routes>
  <Route path="/" element={<Dashboard />} />
  <Route path="/triage" element={<TriageView />} />
  <Route path="/chat" element={<ChatView />} />
  <Route path="*" element={<Navigate to="/" replace />} />
</Routes>
```

- **Actual Fallback Behavior:** Any attempt to directly access `/analysis`, `/traffic`, `/reports`, `/settings`, `/history`, or any arbitrary unknown path (e.g., `/unknown`) matches the catch-all wildcard route (`path="*"`).
- **Redirection:** React Router executes a client-side silent redirection (`<Navigate to="/" replace />`) directly to `/` (`Dashboard`).
- **User Notice Assessment:** There is **no** explanatory notification banner or popup displayed upon redirection; the application cleanly and silently lands the user on the primary Dashboard.

---

## 8. Data and Artifact Integrity (Zero Drift)

SHA-256 cryptographic hashes were taken for all critical model artifacts, preprocessor pipelines, split masks, calibration parameters, and evaluation reports before initiating Task 6 and re-verified upon completion:

| Artifact Path | Pre-Test SHA-256 | Post-Test SHA-256 | Match |
| :--- | :--- | :--- | :---: |
| `data/models/random_forest_balanced.pkl` | `73F9FC5D7986C1CC935E3DCD072CA3CC655E5539F5FDFEB104419113CB43258F` | `73F9FC5D7986C1CC935E3DCD072CA3CC655E5539F5FDFEB104419113CB43258F` | **IDENTICAL** |
| `data/processed/preprocessor_balanced.pkl` | `2FE879FBF70C3C72FBDE6F50C3DC7C86B6E9EDF6F450EE39FDA8053284965169` | `2FE879FBF70C3C72FBDE6F50C3DC7C86B6E9EDF6F450EE39FDA8053284965169` | **IDENTICAL** |
| `data/models_fresh/random_forest_fresh.pkl` | `7573DD297654A7B72517BB1336C03FCA78138515DECFB3CABC1CAD3A4B4F8A24` | `7573DD297654A7B72517BB1336C03FCA78138515DECFB3CABC1CAD3A4B4F8A24` | **IDENTICAL** |
| `data/models_fresh/preprocessor_fresh.pkl` | `0816C8D7488A1D2C0DB7B3F4204F8CA01A88534841C669652C207D6E84C47A43` | `0816C8D7488A1D2C0DB7B3F4204F8CA01A88534841C669652C207D6E84C47A43` | **IDENTICAL** |
| `src/sentinelai/triage/calibrated_params_fresh.json` | `A6B970E33D29274E44D30C068EFD9333DAF58B9D5F55204B844A44DFCFFBF3D0` | `A6B970E33D29274E44D30C068EFD9333DAF58B9D5F55204B844A44DFCFFBF3D0` | **IDENTICAL** |
| `reports/final_fresh_evaluation_report.md` | `5CB220377E4CE9F0D1A3532EB14954CB8FCE92D36675D74BE2D37EE23E864F28` | `5CB220377E4CE9F0D1A3532EB14954CB8FCE92D36675D74BE2D37EE23E864F28` | **IDENTICAL** |
| `reports/fresh_policy_calibration_report.md` | `AC584312C73A21FF473D24ED44EEB2EF5228D3A9232981729361DBBC7836D3B0` | `AC584312C73A21FF473D24ED44EEB2EF5228D3A9232981729361DBBC7836D3B0` | **IDENTICAL** |
| `data/processed_fresh/train_mask_fresh.npy` | `5A1310AAD91AE202F35C44D997BE5F9387714B1887D4EA242BEFB5ECF3C32C6B` | `5A1310AAD91AE202F35C44D997BE5F9387714B1887D4EA242BEFB5ECF3C32C6B` | **IDENTICAL** |
| `data/processed_fresh/val_mask_fresh.npy` | `E497D787FFE9FF2569BB9DFEF0CCC6BA262A2996788927D9883EF90C60555ADC` | `E497D787FFE9FF2569BB9DFEF0CCC6BA262A2996788927D9883EF90C60555ADC` | **IDENTICAL** |
| `data/processed_fresh/test_mask_fresh.npy` | `11C3CC06B3D2A1CF7CF888651E30C34B695751A07CA6C25E3E9A22C02B73D636` | `11C3CC06B3D2A1CF7CF888651E30C34B695751A07CA6C25E3E9A22C02B73D636` | **IDENTICAL** |
| `data/processed_fresh/conflict_mask_fresh.npy` | `5F0564FA6C621B96E4B0095B56981B0CFD027614D0F12362D787BD7AB62F1312` | `5F0564FA6C621B96E4B0095B56981B0CFD027614D0F12362D787BD7AB62F1312` | **IDENTICAL** |

**Byte Drift:** Exactly 0 bytes changed across all 11 core artifacts.

### Database Persistence Audit

- **Initial Alert Count:** 124 records
- **Post-Audit Alert Count:** 158 records (new triage smoke tests recorded without schema corruption)
- **Database Schema Integrity:** Maintained `id`, `timestamp`, `class_id`, `class_label`, `priority`, `decision_status`, `recommended_action`, `confidence`, `explanation`, `explanation_source`, `explanation_provenance`, `shap_explanations`.

---

## 9. Known Failures, Limitations, and Warnings

1. **Third-Party Deprecation Warnings:**
   - Upstream FastAPI `TestClient` uses deprecated Starlette `httpx` bindings.
   - SHAP `TreeExplainer` suggests passing background dataset for future versions when using `feature_perturbation='interventional'`.
2. **Benign False Positive Rate under Two-Stage Policy:**
   - The experimental two-stage policy achieves 99.41% overall policy attack recall on the held-out fresh test split, but exhibits a **1.292% Benign False Positive Rate** (130 benign samples routed to human review or auto-quarantine). This is a known, calibrated trade-off documented in `reports/fresh_policy_calibration_report.md`.
3. **Analyst Review Band Workload:**
   - On the held-out fresh test set, the two-stage policy routes 72.82% of all attacks through the human review band rather than taking unverified automated action. This design guarantees safety but requires SOC capacity.
4. **Unvalidated Model/Policy Pairing:**
   - Running `SENTINELAI_MODEL_VERSION=legacy` alongside `SENTINELAI_TWO_STAGE_TRIAGE=true` is an unvalidated combination. The system explicitly appends operational warnings to alert evidence and uncertainty reasons when this occurs.

---

## 10. Demo Readiness & Portfolio Presentation Guidance

For live demos, recruiter reviews, and technical walkthroughs, present the system as follows:

1. **Standard Baseline Mode (Default):**
   ```bash
   SENTINELAI_MODEL_VERSION=legacy
   SENTINELAI_TWO_STAGE_TRIAGE=false
   ```
   - Demonstrates the stable baseline model and fast deterministic triage routing.
2. **Calibrated Fresh Experimental Mode:**
   ```bash
   SENTINELAI_MODEL_VERSION=fresh
   SENTINELAI_TWO_STAGE_TRIAGE=true
   ```
   - Demonstrates the group-aware trained Random Forest model (93.62% test accuracy) combined with frozen validation-calibrated two-stage triage routing (99.41% attack catch rate).
3. **Key Talking Points:**
   - **Data Hygiene:** 447,915 records partitioned using strict IP-group-aware splitting to prevent synthetic data leakage, with 6,290 conflicting-label flows quarantined.
   - **Explainability:** Real-time SHAP tree feature attributions paired with transparent Laya LLM provenance badges (`groq`, `gemini`, or `template`).
   - **Safety First:** Advisory-only LLM boundaries and explicit analyst-in-the-loop escalation rather than ungrounded autonomous remediation.

---

## Final Audit Sign-Off

- **Backend Pytest Suite:** PASS (141/141)
- **Runtime Smoke Tests:** PASS (All endpoints 200 OK)
- **Model/Policy Matrix:** PASS (4 valid states + fail-fast invalid rejection)
- **Triage Pipeline:** PASS (Benign, Exploits, Shellcode end-to-end verified)
- **Laya Provenance:** PASS (Live Groq + fallback template verified)
- **Frontend Build:** PASS (`npm run build` 0 errors)
- **Artifact Hashes:** PASS (0 byte drift across all 11 critical files)

**Overall Final Assessment:** **PASS WITH WARNINGS** (Ready for demo and production presentation).

