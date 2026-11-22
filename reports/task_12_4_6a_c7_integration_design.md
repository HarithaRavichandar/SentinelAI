# C7 Candidate Integration Design

**Status**: Design for Review (Stage A → Stage B Gate)  
**Date**: 2026-11-21  
**Author**: SentinelAI Team

---

## 1. Current Model Registry Summary

| Version | Model Artifact | Preprocessor Artifact | Default? |
|---------|----------------|----------------------|----------|
| `legacy` | `data/models/random_forest_balanced.pkl` | `data/processed/preprocessor_balanced.pkl` | No |
| `fresh` | `data/models_fresh/random_forest_fresh.pkl` | `data/models_fresh/preprocessor_fresh.pkl` | **Yes** |

**Constants** (`src/sentinelai/inference.py`):
- `SUPPORTED_MODEL_VERSIONS = ("legacy", "fresh")` (line 35)
- `DEFAULT_MODEL_VERSION = "fresh"` (line 34)
- `ENV_MODEL_VERSION = "SENTINELAI_MODEL_VERSION"` (line 32)
- `MODEL_ARTIFACTS` dict maps version → `{model_path, preproc_path}` (lines 38–55)

**Resolution order**: explicit param → `SENTINELAI_MODEL_VERSION` env → `DEFAULT_MODEL_VERSION`

---

## 2. Proposed Change: Register `c7_candidate` as Third Version

Add `"c7_candidate"` to `SUPPORTED_MODEL_VERSIONS` and `MODEL_ARTIFACTS` in `inference.py` only.

```python
SUPPORTED_MODEL_VERSIONS = ("legacy", "fresh", "c7_candidate")

MODEL_ARTIFACTS = {
    "legacy": { ... },
    "fresh": { ... },
    "c7_candidate": {
        "model_path": PROJECT_ROOT / "staging" / "c7_candidate" / "C7_random_forest_depth30_leaf3.pkl",
        "preproc_path": PROJECT_ROOT / "data" / "models_fresh" / "preprocessor_fresh.pkl",  # Reuses Fresh preprocessor
    },
}
```

**No other files modified for registration.**

---

## 3. C7 Artifact Path Mapping

| Artifact | Path | Exists? |
|----------|------|---------|
| Model | `staging/c7_candidate/C7_random_forest_depth30_leaf3.pkl` (~338.68 MiB) | ✅ Yes |
| Preprocessor | `data/models_fresh/preprocessor_fresh.pkl` (shared with Fresh) | ✅ Yes |
| SHA-256 | `staging/c7_candidate/C7_sha256.txt` | ✅ Yes |
| Manifest | `staging/c7_candidate/C7_export_manifest.json` | ✅ Yes |
| Metrics | `staging/c7_candidate/C7_metrics.json` | ✅ Yes |

**Note**: C7 reuses the Fresh preprocessor. No separate preprocessor artifact is created.

---

## 4. Default Model Version

**`DEFAULT_MODEL_VERSION` remains `"fresh"` — no change.**

- `SENTINELAI_MODEL_VERSION` unset → Fresh loads
- Explicit `model_version="c7_candidate"` or `SENTINELAI_MODEL_VERSION=c7_candidate` → C7 loads
- Explicit `model_version="legacy"` or `SENTINELAI_MODEL_VERSION=legacy` → Legacy loads

---

## 5. Rollback Procedure

| Scenario | Action |
|----------|--------|
| Quick rollback | Unset `SENTINELAI_MODEL_VERSION` → defaults to Fresh |
| Per-request rollback | Pass `model_version="fresh"` or `"legacy"` to `InferenceEngine()` |
| API-level | Restart service with `SENTINELAI_MODEL_VERSION=fresh` or unset |

**No code deployment needed** — pure configuration.

---

## 6. C7 Load Failure Behavior

**Mirrors Fresh: raise immediately, no dummy fallback.**

```python
# In InferenceEngine.__init__ (lines 142–147)
if self.model_version == "fresh":
    raise RuntimeError(...)  # ← Add "c7_candidate" to this condition
```

**Rationale**: C7 is a promotion candidate; silent fallback to dummy would mask deployment failures.

---

## 7. New Tests Required (Stage B)

| Test File | Tests to Add |
|-----------|--------------|
| `tests/test_model_selection.py` | • `test_c7_candidate_selection_env` / `test_c7_candidate_selection_param`<br>• `test_missing_c7_model_artifact_raises`<br>• `test_c7_candidate_feature_validation_parity`<br>• `test_c7_candidate_model_preprocessor_pairing` (columns match Fresh)<br>• `test_c7_candidate_shap_explainer` (if SHAP available)<br>• Extend `test_api_predict_reflects_selected_model_version` for C7 |
| `tests/test_inference.py` | • C7 prediction sanity (if not covered above) |
| `tests/test_shap_explanations.py` | • C7 SHAP output structure |

**Reference implementation**: `staging/c7_candidate/test_c7_inference.py` and `test_c7_api_integration.py` patterns.

---

## 8. Files to Modify

| File | Change |
|------|--------|
| `src/sentinelai/inference.py` | Add `"c7_candidate"` to `SUPPORTED_MODEL_VERSIONS` and `MODEL_ARTIFACTS`; update failure condition to include `"c7_candidate"` |

**Only this file** for the registration itself.

---

## 9. Files NOT to Modify

| File / Artifact | Reason |
|-----------------|--------|
| `data/models/random_forest_balanced.pkl` | Legacy model — frozen |
| `data/processed/preprocessor_balanced.pkl` | Legacy preprocessor — frozen |
| `data/models_fresh/random_forest_fresh.pkl` | Fresh model — frozen |
| `data/models_fresh/preprocessor_fresh.pkl` | Fresh preprocessor — shared, frozen |
| `DEFAULT_MODEL_VERSION` constant | Must remain `"fresh"` |
| `SUPPORTED_MODEL_VERSIONS` tuple structure | Only append, never reorder/remove |
| Any test in `tests/` (except new additions) | Existing contracts must not change |

---

## Approval Gate

**This document must be reviewed and approved before Stage B implementation begins.**

- [ ] Registry design correct
- [ ] Artifact paths verified
- [ ] Failure behavior aligned with Fresh
- [ ] Default version unchanged
- [ ] Rollback procedure documented
- [ ] Test scope sufficient
- [ ] "Do not modify" list respected

---

*End of Design Document*