# HW4 Metrics

## N+1 Query Performance

| Page Size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |
|---:|---|---:|---:|---:|---:|
| 10 | naive | 13 | 4.964 | 6.202 | 9.752 |
| 10 | fixed | 4 | 2.950 | 4.836 | 14.870 |
| 50 | naive | 53 | 11.085 | 13.183 | 13.850 |
| 50 | fixed | 4 | 3.096 | 3.541 | 3.816 |
| 200 | naive | 203 | 37.407 | 41.348 | 45.853 |
| 200 | fixed | 4 | 5.494 | 9.177 | 19.221 |

## Median Speed-up

| Page Size | p50 Speed-up | Median Latency Reduction |
|---:|---:|---:|
| 10 | 1.68x | 40.6% |
| 50 | 3.58x | 72.1% |
| 200 | 6.81x | 85.3% |

The fixed implementation scales better because the naive endpoint executes an additional related-data query for each clinical trial, while the fixed endpoint uses eager loading.

## RAG Configuration

- Documents: 5
- Chunks: 7
- Chunk size: 500
- Chunk overlap: 50
- Embedding model: nomic-embed-text
- Generation model: qwen3:8b
- Vector store: FAISS
- Default top_k: 3

## Top-K Sweep

| k | Observation |
|---:|---|
| 1 | Incomplete context; only blinding evidence retrieved |
| 3 | Best balance; both blinding and randomization evidence retrieved |
| 5 | Required evidence retrieved, but additional irrelevant context introduced |

## RAG Refusal Results

- Q5: Context-engineered RAG correctly refused.
- Q6: Context-engineered RAG correctly refused.