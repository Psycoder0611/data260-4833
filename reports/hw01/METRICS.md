# Non-Determinism Experiment Metrics

Model: `qwen3:8b`

Fixed input: `reports/hw01/cases/nondeterminism_input.json`

| Metric | Temp 0.7 | Temp 0.0 |
|---|---|---|
| Distinct tag sets | 17 | 2 |
| Tags in all 20 runs | None | Blood Glucose Control, Clinical Trials, Type 2 Diabetes |
| Tags in exactly 1 run | Clinical Drug Trials, Clinical Trial Drug Development, Clinical Trial Innovation, Clinical Trial Medication, Clinical Trial Research, Clinical Trial for Diabetes Medication, Diabetes Medication Development, Diabetes Medication Trial | None |
| Latency p50 (ms) | 239054.34 | 233503.43 |
| Latency p95 (ms) | 315536.01 | 255039.31 |
| Latency p99 (ms) | 342524.06 | 255811.00 |


## Interpretation

The results show that temperature had a clear effect on the consistency of the model's output. At temperature 0.7, I observed 17 different tag sets across 20 runs, and no individual tag appeared in every run. In comparison, temperature 0.0 produced only 2 different tag sets, and the tags "Blood Glucose Control", "Clinical Trials", and "Type 2 Diabetes" appeared in all 20 runs.

This means that two users submitting the exact same input could receive noticeably different tags when the model is run at a higher temperature. At temperature 0.0, they would be much more likely to receive the same or very similar output.

Some run-to-run variation can be acceptable for tasks such as brainstorming tag suggestions, where different reasonable answers may still be useful. However, this kind of variation would not be acceptable for a high-stakes task such as determining whether a clinical trial meets a required safety or eligibility rule, where consistent results would be important.

The latency was also somewhat more variable at temperature 0.7. Its p95 and p99 latency values were higher than those at temperature 0.0, although both configurations required several minutes per complete Planner, Reviewer, and Finalizer run.