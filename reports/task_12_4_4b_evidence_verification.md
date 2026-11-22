# Evidence Verification Report – Frontend Compatibility

**Report generated:** 2026-11-20

---

## A. `/alerts` verification

- **HTTP method & decorator**: `@app.get("/alerts")` – defined in `src/sentinelai/api.py` lines **476‑478**.
- **Handler function**:
```python
@app.get("/alerts")
def list_alerts(limit: int = Query(50, ge=1, le=500)) -> List[Dict[str, Any]]:
    return get_alerts(limit=limit)
```
- **Storage call**: `get_alerts` from `src/sentinelai/storage/db.py` lines **210‑238**.
- **Returned JSON structure** (each alert dict, keys exactly as selected in the SQL query):
```json
[
  {
    "id": 123,
    "timestamp": 1700456789123,
    "class_id": 3,
    "class_label": "DoS",
    "probabilities": {"0": 0.01, "1": 0.05, ... "9": 0.02},
    "latencyMs": 12.3,
    "priority": "high",
    "decision_status": "final",
    "recommended_action": "quarantine",
    "decision_confidence": 0.92,
    "requires_human_review": false,
    "policy_mode": "legacy",
    "decision": { /* may be present if decision_json was stored */ },
    "explanation": "<LLM text>",
    "explanation_source": "gemini"
  }
]
```
- **Raw flow features**: **Not persisted** – the `INSERT` statement in `insert_alert` (see `src/sentinelai/storage/db.py` lines **184‑200**) explicitly omits any raw feature payload. Therefore alerts never contain a `features` field.
- **Prediction / explanation / decision data**: The alert includes the model prediction (`class_id`, `class_label`, `probabilities`) and any LLM explanation (`explanation`, `explanation_source`). If a triage decision was generated, its serialized fields are stored (`priority`, `decision_status`, `recommended_action`, `decision_confidence`, `requires_human_review`, `policy_mode`, optional `decision_json`). No nested `prediction` object is present.
- **Frontend TypeScript contract**: `AlertRecord` defined in `frontend/src/components/AlertStatsContext.tsx` lines **15‑30** matches the backend fields **except** the earlier report’s claim of a nested `prediction` object and a `features` field. The actual interface includes `class_id`, `class_label`, `probabilities`, and the decision metadata fields – which aligns with the real backend payload.

## B. `/decision` verification

- **HTTP method & decorator**: `@app.post("/decision")` – defined in `src/sentinelai/api.py` lines **486‑488**.
- **Handler function**:
```python
@app.post("/decision")
def get_decision(payload: Dict[str, Any], explain_shap: bool = Query(False)) -> Dict[str, Any]:
    triage_res = triage(payload, explain_shap=explain_shap)
    return triage_res["decision"]
```
- **Logic**: Calls the **same `triage` function** used by the `/triage` endpoint (see `src/sentinelai/api.py` lines **359‑474**). It runs a prediction, optional SHAP, builds a decision via `evaluate_triage_decision`, and finally extracts the `decision` field from the full triage response.
- **Returned JSON structure** – exactly the `decision` object produced by the decision engine (see `src/sentinelai/triage/decision_engine.py` lines **425‑447**). Example:
```json
{
  "priority": "high",
  "recommended_action": "quarantine",
  "decision_confidence": 0.92,
  "decision_status": "final",
  "requires_human_review": false,
  "policy_mode": "legacy",
  "evidence": {"prediction": {...}, "shap": {...}},
  "uncertainty_reasons": []
}
```
- **Behavior when no prior triage exists**: The endpoint does **not** read any stored decision; it always performs a fresh triage on the supplied payload. If the payload is invalid, a `400` HTTPException is raised before reaching the decision logic.
- **Mismatch correction**: The previous report described `/decision` as a `GET` returning `engine.decision_info`. The actual implementation is a **POST** that re‑executes the full triage pipeline and returns only the `decision` sub‑object.

## C. `/triage` verification (full response)

- **Top‑level response fields** (as assembled in `src/sentinelai/api.py` lines **359‑474**):
  - `class_id`, `class_label`, `probabilities` – from model prediction.
  - `explanation`, `explanation_source`, `explanation_provenance` – LLM explanation.
  - **Optional SHAP fields** (when `explain_shap=True`):
    - `shap_status` (e.g., "unavailable" or "available")
    - `shap_reason` (error message if unavailable)
    - `shap_explanations` (the raw dict returned by `engine.explain_shap`).
  - `decision` – the decision engine’s model‑dumped dict (see `decision_engine.evaluate_triage_decision`).
  - `latencyMs` – total latency for the request.
  - `id` – the newly inserted alert row ID (if persistence succeeded).
- **Optional fields** are added only if their corresponding step succeeded; otherwise they are omitted.
- **Decision sub‑object** contains the fields listed in section B.

## D. Frontend compatibility check

| Backend field | Frontend TypeScript interface | Match / Mismatch | Notes |
|---|---|---|---|
| `id`, `timestamp`, `class_id`, `class_label`, `probabilities` | `AlertRecord` (lines **15‑20**) | ✅ | Direct mapping.
| `latencyMs` | `AlertRecord.latencyMs` | ✅ | Present.
| `priority`, `decision_status`, `recommended_action`, `decision_confidence`, `requires_human_review`, `policy_mode` | `AlertRecord` fields (lines **23‑28**) | ✅ | Align.
| `explanation`, `explanation_source` | Not part of `AlertRecord` but used internally; not displayed in UI. No mismatch needed.
| `decision` (object) | `AlertRecord.decision` (type `AlertDecisionMetadata`, lines **4‑13**) | ✅ | Fields correspond.
| **Incorrect claim** in prior report: nested `prediction` object inside each alert and a `features` field. **Reality**: those fields do **not** exist; the frontend does not expect them, and the backend does not provide them.
| `/decision` endpoint method** – prior report said `GET`; actual is **POST** returning only the decision object. Frontend never calls `/decision` directly; the UI uses `/triage` and extracts `decision` from the full response.

**Summary of mismatches fixed**:
- Removed non‑existent `prediction` and `features` keys from the `/alerts` description.
- Corrected HTTP method for `/decision` to POST and clarified it recomputes triage.
- Updated JSON examples to reflect the real schema produced by the storage layer and decision engine.
- Confirmed that all TypeScript interfaces (`AlertRecord`, `AlertDecisionMetadata`) are in sync with the actual backend payloads.

---

## Conclusion

The corrected evidence verification now accurately reflects the source‑level contracts of `/alerts`, `/decision`, and `/triage`. The frontend TypeScript contracts are consistent with the real backend responses, and no further code changes are required.
