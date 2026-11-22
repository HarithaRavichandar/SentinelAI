# SentinelAI — C7 Promotion‑Readiness Report (Task 12.4.5R)

---

## 1. Artifact Integrity – VERIFIED
- **Model artifact:** `staging/c7_candidate/C7_random_forest_depth30_leaf3.pkl`
- **Computed SHA‑256:** `d3e0f429842a5a35628b0cd4fcf20469e33154c810a3f76e77506b0a99d2a05e`
- **Reference files:** `staging/c7_candidate/C7_sha256.txt` and `staging/c7_candidate/C7_export_manifest.json` contain the identical hash.
- **Conclusion:** All three checksum values match – the C7 artifact integrity check **passes**.

---

## 2. Overall Test‑Based Performance Metrics
| Metric | Fresh | C7 | Δ (percentage points) |
|---|---:|---:|---:|
| Accuracy | 93.6266 % | 93.4155 % | **‑0.2111** |
| Balanced accuracy | 54.4074 % | 65.4448 % | **+11.0374** |
| Macro F1 | 59.5387 % | 63.3369 % | **+3.7982** |
| Weighted F1 | 93.5367 % | 93.6494 % | **+0.1127** |
| Benign precision | 99.2523 % | 99.9410 % | **+0.6887** |
| Benign recall | 98.5285 % | 97.9149 % | **‑0.6136** |

*The overall accuracy drops slightly, but balanced accuracy and macro‑F1 improve markedly, indicating a better handling of minority classes.*

---

## 3. Per‑Class F1 Comparison
| Class | Support | Fresh F1 | C7 F1 | Δ pp | Regression? |
|---|---:|---:|---:|---:|---|
| Benign | 53 618 | 0.9889 | 0.9892 | +0.03 | No |
| Analysis | 57 | 0.2828 | 0.5109 | +22.81 | No |
| Backdoor | 61 | 0.6000 | 0.5818 | **‑1.82** | **Yes** |
| DoS | 667 | 0.4312 | 0.4690 | +3.78 | No |
| Exploits | 4 606 | 0.7730 | 0.7854 | +1.24 | No |
| Fuzzers | 3 966 | 0.7191 | 0.7098 | **‑1.30** | **Yes** |
| Generic | 683 | 0.7822 | 0.7889 | +0.67 | No |
| Reconnaissance | 1 894 | 0.6297 | 0.6180 | **‑1.17** | **Yes** |
| Shellcode | 265 | 0.2941 | 0.3577 | +6.36 | No |
| Worms | 35 | 0.4528 | 0.5231 | +7.03 | No |

**Interpretation notes**
- The three classes that regress (Backdoor, Fuzzers, Reconnaissance) have modest support, but the drops are measurable.
- Analysis, DoS, Exploits, Generic, Shellcode and Worms show clear improvements.
- Benign F1 improves marginally.
- Per‑class precision and recall values were not part of the verified evidence and are therefore omitted.

---

## 4. Regression / Test Evidence
- **Core regression suite** (full core tests): `143 passed, 28 warnings` (no failures).
- **C7 API integration tests**: `11 passed`.
- **C7 SHAP tests**: `2 passed, 1 warning`. The SHAP test permits an *unavailable* fallback when the SHAP library is missing; successful SHAP computation is **not conclusively demonstrated**.
- **C7 inference & validation tests**: passed.

No failures were observed, but the test runs were separate; the core suite does not automatically include the C7‑specific tests.

---

## 5. Model Selection & Rollback Mechanics
- `src/sentinelai/inference.py` defines `SUPPORTED_MODEL_VERSIONS = ("legacy", "fresh")`.
- The environment variable `SENTINELAI_MODEL_VERSION` is read, but any value other than `legacy` or `fresh` raises `ModelConfigurationError`.
- Consequently, setting `SENTINELAI_MODEL_VERSION=c7_candidate` **will not activate** the C7 model under the current code.
- **Future requirement:** extend `InferenceEngine` (e.g., add `c7_candidate` to `SUPPORTED_MODEL_VERSIONS` and register its artifact path) and provide a reversible registration/rollback pathway.

---

## 6. Frontend Compatibility (source‑level audit)
- **`/alerts`** – GET – returns flat alert records (no nested prediction payload). ✅
- **`/decision`** – POST – returns the decision object (prediction, optional decision metadata). ✅
- **`/triage`** – POST – returns prediction, optional SHAP explanation (when available), and decision data. ✅
- **SHAP** is accessed through the `/triage` endpoint; the frontend calls the corresponding API wrapper, but the actual SHAP payload depends on successful backend computation.
- The audit was performed strictly by reading source code; no live browser‑to‑backend verification was performed.

---

## 7. Runtime & Resource Summary
- **C7 model size:** ~338.68 MiB (from `C7_export_manifest.json`).
- **Fresh model size:** ~886 MiB (reported in the Fresh model artifact documentation).
- **Isolated prediction latency (single sample):** ~0.2454 s.
- **Full test‑partition prediction time:** ~1.2651 s.
- **Host machine:** 7.68 GiB RAM, with limited free memory observed during earlier test runs.

---

## 8. Open Issues / Blockers
1. **SHAP computation verification** – The SHAP test allows a fallback; successful SHAP values have not been proved.
2. **Benign recall decrease** – Recall drops by ~0.61 pp; impact on detection sensitivity should be evaluated.
3. **Model registration** – C7 is not currently loadable via `InferenceEngine`; code changes and a vetted rollout procedure are required.
4. **Operational validation** – No live end‑to‑end deployment test (frontend‑backend integration under load) has been performed.

---

## 9. Final Verdict
**B — Ready only after specific blockers are resolved**

### Reasoning
- **Performance suitability:** Balanced accuracy and macro‑F1 improvements outweigh the small overall accuracy loss; class‑level gains are significant for several minority classes.
- **Artifact integrity:** Verified via matching SHA‑256 checksums.
- **Backend integration:** Isolated C7 tests pass, but full pipeline integration (model registration, SHAP validation) is missing.
- **Frontend:** Source‑level compatibility confirmed; functional UI verification pending.
- **Operational readiness:** Not established – memory headroom, latency under production load, and SHAP availability remain open.

### Required Conditions before Promotion
1. **Confirm SHAP success** (or explicitly document its unavailability) and update the `/triage` contract accordingly.
2. **Quantify impact of the reduced Benign recall** on detection metrics and decide if the trade‑off is acceptable.
3. **Implement a reversible C7 registration mechanism** in `InferenceEngine` (add to `SUPPORTED_MODEL_VERSIONS`, map to the staging artifact, and provide a safe rollback to `fresh`).
4. **Conduct a controlled deployment** (e.g., canary or shadow mode) to validate end‑to‑end behavior, resource usage, and latency under realistic traffic.

Once these blockers are addressed, the C7 candidate can be reconsidered for production promotion.

---

*Report generated on 2026‑11‑20.*