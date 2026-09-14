# HW2 Metrics

## Configuration

- SID4: 4833
- PORT_BASE: 8333
- PREFIX: s4833
- SEED: 4833
- VERIFY_SEED: 264833
- DOMAIN_ID: 1
- Domain: Clinical Trial Listings
- Local model: qwen3:8b

---

## 1. Schema Validation Experiment

I use the same frozen input from:

`reports/hw02/cases/schema_input.json`

for all 30 runs.

### Results

| Outcome | Count |
|---|---:|
| Valid on first attempt | 30 |
| Valid after 1 retry | 0 |
| Valid after 2+ retries | 0 |
| Hit turn ceiling | 0 |
| Total | 30 |

Completion rate: **100%**

Mean latency: **91,121.70 ms**  
Approximate mean latency: **91.12 seconds**

All 30 runs produced Planner outputs that passed the Pydantic schema on the first attempt.

---

## 2. Turn Ceiling Comparison

I compare the same frozen input using two Planner-attempt ceilings.

| Turn Ceiling | Completed Runs | Completion Rate | Mean Latency |
|---|---:|---:|---:|
| 2 | 20/20 | 100.0% | 94,650.37 ms |
| 10 | 20/20 | 100.0% | 89,413.78 ms |

### Interpretation

Both ceiling settings achieved a 100% completion rate.

The ceiling-10 runs had a slightly lower observed mean latency in this experiment, but both configurations completed successfully on the first Planner attempt in most normal cases.

For deployment, I prefer the smaller ceiling because it provides a tighter bound on repeated Planner corrections while maintaining the same observed completion rate.

---

## 3. Adversarial Experiment

I use the adversarial input from:

`reports/hw02/cases/adversarial_input.json`

The input encourages extremely short tags such as `AI`, `ML`, and `X`, which violate the Pydantic requirement that every tag must contain between 3 and 30 characters.

### Result

- Runs: 5
- Ceiling hits: **5/5**
- Ceiling-hit rate: **100%**

The Pydantic validator correctly rejected the short tags and the Supervisor routed according to the configured Planner-attempt ceiling.

For this bounded adversarial test, I used a Planner-attempt ceiling of **1** so the experiment terminates after the invalid proposal is reviewed instead of starting another potentially long local-model correction call.

---

## 4. Pydantic Schema

The Planner output is required to contain:

- Exactly 3 tags
- Every tag must be a string
- Every tag must contain 3–30 characters
- Summary must contain no more than 25 words

Invalid outputs are returned as Reviewer feedback and can be routed back to the Planner while the configured Planner-attempt ceiling permits another correction.

---

## 5. Raw Result Files

Machine-readable results are stored in:

- `reports/hw02/raw/schema_runs.csv`
- `reports/hw02/raw/schema_runs.json`
- `reports/hw02/raw/ceiling_2_runs.csv`
- `reports/hw02/raw/ceiling_2_runs.json`
- `reports/hw02/raw/ceiling_10_runs.csv`
- `reports/hw02/raw/ceiling_10_runs.json`
- `reports/hw02/raw/adversarial_runs.csv`
- `reports/hw02/raw/adversarial_runs.json`