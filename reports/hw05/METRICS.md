# HW5 Metrics

## Part 3 - Fault Injection Results

| Injected Failure Rate | Success Rate | Mean Latency (ms) | p99 Latency (ms) |
|---|---:|---:|---:|
| 0% | 100.0% | 0.058 | 0.200 |
| 20% | 98.0% | 3.512 | 37.778 |
| 50% | 94.0% | 11.039 | 38.326 |

Total calls: 150  
Calls per failure rate: 50  
VERIFY_SEED: 264833

## Part 5 - Local Ollama Agent Scenarios

Model: qwen3:8b

| Scenario | Step Count | Tool-Call Count | Stop Reason |
|---|---:|---:|---|
| Search trial | 2 | 1 | normal_completion |
| Trial details | 2 | 1 | normal_completion |
| Organization summary | 2 | 1 | normal_completion |
| Safety rule scenario | 1 | 0 | normal_completion |