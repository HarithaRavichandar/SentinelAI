# Random Forest – Class‑weighting Evaluation

**Configuration:** class_weight=`balanced_subsample`

**Accuracy:** 0.9295

## Per‑class metrics

- Class 0: precision=0.992, recall=0.983, f1=0.988, support=53605
- Class 1: precision=0.289, recall=0.183, f1=0.224, support=60
- Class 2: precision=0.844, recall=0.474, f1=0.607, support=57
- Class 3: precision=0.627, recall=0.285, f1=0.392, support=642
- Class 4: precision=0.763, recall=0.799, f1=0.780, support=4716
- Class 5: precision=0.637, recall=0.815, f1=0.715, support=4259
- Class 6: precision=0.868, recall=0.735, f1=0.796, support=664
- Class 7: precision=0.772, recall=0.603, f1=0.677, support=2826
- Class 8: precision=0.128, recall=0.206, f1=0.158, support=315
- Class 9: precision=0.655, recall=0.442, f1=0.528, support=43

## Confusion Matrix

```52713	11	3	10	119	660	5	69	15	0
16	11	0	6	27	0	0	0	0	0
1	0	27	0	11	13	0	5	0	0
12	3	0	183	280	117	13	26	7	1
93	12	1	42	3766	549	27	208	14	4
209	1	1	18	325	3471	22	165	47	0
11	0	0	9	65	75	488	9	3	4
62	0	0	16	286	397	4	1705	355	1
11	0	0	8	47	162	3	19	65	0
1	0	0	0	12	8	0	3	0	19
```
