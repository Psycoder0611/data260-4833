# HW3 Retrieval Metrics

The same five precommitted questions and the same
`sentence-transformers/all-MiniLM-L6-v2` embedding model were used for all
three retrieval techniques. Top-k was fixed at 3.

| Technique       |   Top-1 Cosine |   Mean@3 Cosine |   # Chunks |   Avg Chunk Length |   Avg Retrieval Latency (ms) |   Recall@3 |
|:----------------|---------------:|----------------:|-----------:|-------------------:|-----------------------------:|-----------:|
| Token           |         0.591  |          0.5611 |         19 |            1875.84 |                        10.26 |          1 |
| Semantic        |         0.5683 |          0.533  |         10 |            3269.2  |                         8.12 |          1 |
| Sentence-Window |         0.5267 |          0.5008 |        115 |             284.28 |                        10.9  |          1 |

## Metric definitions

- **Top-1 Cosine:** Average cosine similarity of the rank-1 result across the five questions.
- **Mean@3 Cosine:** Average cosine similarity across all top-3 retrieved results.
- **# Chunks:** Number of chunks/nodes created from the full three-document corpus.
- **Avg Chunk Length:** Average character length of all chunks/nodes created by that technique.
- **Avg Retrieval Latency (ms):** Mean retrieval time across the five questions, counted once per question.
- **Recall@3:** Fraction of questions whose expected source file appears anywhere in the top-3 results.
