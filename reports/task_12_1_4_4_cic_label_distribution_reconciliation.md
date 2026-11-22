# CIC Label Distribution Reconciliation

**File examined**: `H:\SentinelAI\data\external\cic_ids_2018\cic.csv`

## Audited statistics
| Metric | Value |
|--------|-------|
| File size (bytes) | 358,223,333 |
| Approx. size (MiB) | 341.6 MB |
| Total data rows (excl. header) | 1,048,575 |
| Column count (including metadata columns) | 80 |

## Raw label distribution (as read directly from the CSV)
| Label (exact) | Row count |
|---------------|----------|
| Benign | 667,626 |
| FTP‑BruteForce | 193,360 |
| SSH‑Bruteforce | 187,589 |

*No other distinct label values were present in the file.*

## Comparison with the design document
The design document `reports/task_12_1_4_2_final_cic_experimental_design_review.md` defines **nine** experiment‑specific labels:
```
BENIGN, DoS, DDoS, Bot, Recon, Web Attack, Infiltration, Backdoor, PortScan
```
and lists the following row counts (sum = 2,873,249):
- BENIGN: 1,362,862
- DoS: 603,812
- DDoS: 302,058
- Bot: 151,029
- Recon: 120,823
- Web Attack: 121,224
- Infiltration: 90,618
- Backdoor: 60,412
- PortScan: 60,411

### Discrepancies
| Aspect | Design doc | Audited file | Difference |
|--------|------------|--------------|------------|
| Total rows | 2,873,249 | 1,048,575 | **-1,824,674** rows (≈ 63 % fewer) |
| Label set | 9 distinct values | 3 distinct values (Benign, FTP‑BruteForce, SSH‑Bruteforce) | 6 missing classes |
| BENIGN count | 1,362,862 | 667,626 | -695,236 |
| DoS / DDoS / … | non‑zero | 0 | — |

The audit reveals that the CSV file contains **only three** raw label strings, none of which match the nine experiment‑specific labels (except for *Benign* which differs only by case). Consequently the previously reported nine‑class counts cannot be derived from this file.

## Impact on the nine‑class experiment
- **Label mismatch**: The dataset does not provide the required eight attack categories (DoS, DDoS, Bot, Recon, Web Attack, Infiltration, Backdoor, PortScan). Any model trained on this CSV would effectively be a **three‑class** problem (Benign vs two attack types).
- **Row‑count shortfall**: With ~1.05 M rows versus the ~2.87 M rows assumed in the design, the statistical power of the experiment would be reduced substantially.
- **Mapping feasibility**: A naïve mapping (e.g., treating *FTP‑BruteForce* and *SSH‑Bruteforce* as a generic “Attack” class) would collapse the intended granularity and invalidate the nine‑class evaluation protocol.

## Recommendations
1. **Obtain the full CIC‑IDS2018 label set**: Ensure you are using the original unfiltered CSV (or the official dataset split) that contains all nine attack categories.
2. **Re‑align label taxonomy**:
   - Convert the raw label strings to the nine‑class IDs (e.g., map `Benign` → `BENIGN`, `FTP‑BruteForce` / `SSH‑Bruteforce` → appropriate attack class if they belong to one of the nine, otherwise treat them as “Other” and exclude).
   - Verify that each of the nine classes appears with a sufficient number of rows.
3. **Update the design document**: Replace the erroneous row counts with the audited values once the correct dataset is in place.
4. **If a three‑class experiment is acceptable**: Adjust the design to reflect only the three observed classes, revise the label mapping, and recompute class distribution statistics.

---
*All measurements were performed in a read‑only manner; no files were modified.*
