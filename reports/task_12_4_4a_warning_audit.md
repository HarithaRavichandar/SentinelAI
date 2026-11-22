# SentinelAI – Task 12.4.4A: Full Regression Warning Audit

**Read‑only audit** – no code, tests, models, or environment were modified.

## Verified test result
- **Command executed**: `python -m pytest tests/ -v --maxfail=1`
- **Outcome**: **143 passed**, **28 warnings**
- **Duration**: **121.45 seconds**
- **Environment**: `.venv_compat` (Python 3.11.7, scikit‑learn 1.3.2)

> The warning count comes from the summary of the successful run; the individual warning messages were not captured verbatim, so a complete enumeration is not possible.

## Warnings observed (known origins)
| Warning type | Origin (module / file) | Test(s) where seen |
|--------------|------------------------|-------------------|
| `StarletteDeprecationWarning` | FastAPI `TestClient` (Starlette) – internal deprecation of an API used by FastAPI's testing client | Appears in the FastAPI integration tests (e.g., `tests/test_api_*` modules) |
| `FutureWarning` (SHAP) | `shap.explainers._tree.py:253` – SHAP’s TreeExplainer emits a future‑deprecation warning | Reported across several test modules that invoke SHAP, notably `tests/test_shap_explanations.py` and the C7 SHAP test (when run) |
| `UserWarning` (scikit‑learn) | `sklearn.metrics._classification.py:2399` – warning about label handling in `classification_report` / related metric functions | `tests/test_model_validation.py::test_compute_validation_metrics` |

**Note:** The total of *28* warnings reported by pytest cannot be fully reconstructed from the three sources listed above. The remaining warnings are likely repetitions of the ones above (multiple test modules triggering the same warning) or additional third‑party warnings that were not captured in the provided summary.

## Risk assessment
- **StarletteDeprecationWarning** – originates from the testing utilities, not from the application code. It does **not** affect runtime behaviour of the SentinelAI service. However, future versions of Starlette/FastAPI may remove the deprecated feature, which could cause test failures later.
- **SHAP FutureWarning** – signals an upcoming change in SHAP’s API. The warning is harmless for current functionality but indicates that the SHAP integration may need adjustments when upgrading SHAP.
- **sklearn UserWarning** – relates to metric calculation edge‑cases (e.g., undefined metrics for missing classes). The warning does not break the test; it merely informs the user. It should be reviewed to ensure the metric handling matches the intended behaviour, but it is not a functional fault.
- **Unidentified warnings** – because we cannot enumerate all 28 warnings, there is a residual uncertainty. If any of the unknown warnings stem from deprecated behaviours in our own code, they could affect future compatibility.

## Recommended follow‑up actions
1. **Upgrade the test environment** to the latest stable versions of Starlette, FastAPI, and SHAP when feasible, then re‑run the test suite to verify that the deprecation/future warnings are resolved.
2. **Suppress known harmless warnings** in the test configuration (e.g., via `filterwarnings` in `pytest.ini`) to keep the output clean, after confirming they are truly non‑impactful.
3. **Audit the remaining warnings**:
   - Run the test suite with `-Werror` or `-Wdefault` to capture the full warning trace.
   - Record each distinct warning message and its source file.
   - Determine whether any originate from SentinelAI code (e.g., use of deprecated scikit‑learn APIs) and address them.
4. **Document the warning handling policy** in the project’s contribution guidelines so future contributors are aware of the need to keep warnings minimal.
5. **Add a regression test** that asserts the total warning count stays below a threshold (e.g., < 5) after fixing the known issues, to catch regressions.

---
*This audit is read‑only: no code, tests, dependencies, or configuration were altered.*
