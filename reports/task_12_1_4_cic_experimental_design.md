# CIC Experimental Design – Task 12.1.4.1 (Corrected)

---

## 1. Label taxonomy (experiment‑specific IDs)

The nine labels verified in **Task 12.1.2** are used **exactly** as listed below.  The integer IDs are **new experiment‑specific identifiers** and **do not** map to any existing SentinelAI model.

| Integer ID | Label |
|------------|-------|
| 0 | **BENIGN** |
| 1 | **DoS** |
| 2 | **DDoS** |
| 3 | **Bot** |
| 4 | **Recon** |
| 5 | **Web Attack** |
| 6 | **Infiltration** |
| 7 | **Backdoor** |
| 8 | **PortScan** |

All previous references to `FTP‑Patator`, `SSH‑Patator`, and `Botnet` have been **removed**.

---

## 2. Model feature‑schema claims

* The **Legacy** and **Fresh** Random Forest model files (`random_forest_balanced.pkl` and `random_forest_fresh.pkl`) have **not** been inspected; therefore:
  * We **do not** claim either model uses 75 features.
  * We **do not** claim the existing preprocessing expects exactly 75 features.
  * The actual model dimensionality and any feature‑importance values are **UNKNOWN**.
* **CWR Flag Count** is **absent** from the CIC CSV (`cic.csv`).
* **CWE Flag Count** **is present** in the CIC CSV and is a distinct feature – it is **not** a substitute for `CWR Flag Count`.
* Two experimental feature schemas remain viable:
  * **Schema A – SentinelAI‑aligned**: 75 features that match the historical SentinelAI feature list (excluding `CWE Flag Count`).
  * **Schema B – CIC‑native**: 76 features – the full set from the CIC CSV, including `CWE Flag Count`.
* **No claim** is made that either schema is equivalent to the (as‑yet‑uninspected) existing models.

---

## 3. Duplicate‑group handling strategy

Future implementation must:
1. **Group exact‑feature duplicates** (rows whose 75‑ or 76‑dimensional feature vectors are identical).
2. **Inspect each duplicate group** for conflicting labels:
   * If all rows in a group share the same label → keep a single representative (or keep all, but ensure they stay in the same partition).
   * If a group contains **conflicting labels**, **report** the group separately and **exclude** it from training/validation/test partitions.
3. **Prevent duplicate groups from crossing partitions** (train/validation/test).  The split algorithm must assign each duplicate group **as a whole** to a single partition.
4. **Maintain an audit trail** (e.g., a CSV log) that records:
   * Group identifier (hash of the feature vector).
   * Number of rows in the group.
   * Labels present.
   * Reason for exclusion (if applicable).

---

## 4. Split protocol (proposed approaches)

| Approach | Description | When applicable | Limitations |
|----------|-------------|----------------|------------|
| **Random stratified split** | Stratified on the nine labels to preserve class proportions. | Baseline when no temporal or session information is reliable. | May leak information if rows from the same capture/session appear in different partitions. |
| **Chronological split** | Order rows by timestamp (if a reliable timestamp column exists) and split by time (e.g., earliest 70 % → train, next 15 % → validation, latest 15 % → test). | Useful when timestamps reflect data collection chronology. | The CIC CSV timestamps have **not** been validated; their reliability is unknown. |
| **Group‑based split** | Identify capture or session identifiers (e.g., file‑name prefixes, flow‑session IDs) and keep all rows from the same identifier within a single partition. | Preferred if such identifiers can be recovered from the data or metadata. | No explicit session identifiers are currently documented; extracting them may require additional investigation. |

No claim is made that any split guarantees capture‑independent generalisation; the chosen split should be documented and its assumptions clarified.

---

## 5. Preprocessing and model recommendations

* **Preprocessing** – All steps (e.g., scaling, imputation) must be **fit on the training partition only** and then applied to validation and test partitions.
* **Scaler reuse** – The existing SentinelAI `StandardScaler` **cannot** be reused without inspection; a fresh scaler will be instantiated for the experiment.
* **Baseline model** – `DummyClassifier` (most‑frequent class) to establish a lower bound.
* **Candidate models** –
  * `RandomForestClassifier`
  * `ExtraTreesClassifier`
  * `GradientBoostingClassifier` – to be considered **only after** confirming library compatibility and computational feasibility on the CIC data size.
* **Class‑weight handling** – Not all models support `class_weight='balanced'` in the same way; each model’s documentation should be consulted before applying it.
* **SMOTE** – Optional oversampling of minority classes; must be applied **after** the training‑only split and **before** model fitting, with careful documentation of any synthetic samples introduced.

---

## 6. Reproducibility status (all future activities are **PROPOSED**)

| Activity | Status |
|----------|--------|
| Train/validation/test index creation | **PROPOSED** |
| Scaler fitting on training data | **PROPOSED** |
| Duplicate‑group detection & partitioning | **PROPOSED** |
| Model training (all candidates) | **PROPOSED** |
| Hyper‑parameter tuning | **PROPOSED** |
| Final test evaluation & metric computation | **PROPOSED** |

All steps will be documented with random seeds (where applicable) and version information once implementation proceeds.

---

## 7. Implementation‑readiness decision

**NOT READY** – The experiment cannot be executed until:
1. Actual model metadata (feature counts, importance values) are inspected.
2. A concrete duplicate‑group and conflicting‑label handling procedure is implemented.
3. Timestamp provenance and/or session identifiers are assessed for the CIC dataset.

---

## 8. Summary of changes made

* Added a **new label taxonomy** with the nine verified labels and integer IDs.
* Removed all references to unsupported labels (`FTP‑Patator`, `SSH‑Patator`, `Botnet`).
* Updated feature‑schema section to reflect **UNKNOWN** model dimensions and to clarify the status of `CWR Flag Count` and `CWE Flag Count`.
* Re‑written duplicate‑group strategy to avoid blind removal and to handle conflicting labels.
* Expanded split‑protocol discussion to include random, chronological, and group‑based options, and removed any claim of capture‑independent generalisation.
* Clarified preprocessing and model‑recommendation statements, removing assumptions about reusing existing scalers or uniform class‑weight support.
* Marked all future implementation steps as **PROPOSED** rather than completed.
* Set the overall implementation‑readiness decision to **NOT READY**.

No other files in the repository were modified.

---

*Prepared by Antigravity (AGY) – November 2026*