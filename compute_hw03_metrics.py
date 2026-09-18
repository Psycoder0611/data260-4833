"""
DATA 260 - Homework 3
Section 2.6: Retrieval Metrics

This script reads the three raw retrieval CSV files produced by
run_hw03_retrieval.py and creates the comparison table used in METRICS.md.

Metrics:
- Top-1 cosine similarity: average cosine similarity of the rank-1 result
  across the five fixed questions.
- Mean@3 cosine similarity: average cosine similarity across all top-3 results.
- Number of chunks/nodes created by each chunking strategy.
- Average chunk/node length from the completed chunking runs.
- Average retrieval latency: averaged once per question (not once per rank).
- Recall@3: fraction of questions for which the expected source appears
  anywhere in the top-3 retrieved results.
"""

from pathlib import Path
import pandas as pd

RAW_DIR = Path("reports/hw03/raw")
METRICS_FILE = Path("reports/hw03/METRICS.md")
TOP_K = 3

# These values come from the completed chunking runs in RUN_LOG.txt.
# They describe the full indexed corpus, not only the retrieved top-k rows.
CHUNKING_STATS = {
    "Token": {
        "num_chunks": 19,
        "avg_chunk_len": 1875.84,
    },
    "Semantic": {
        "num_chunks": 10,
        "avg_chunk_len": 3269.20,
    },
    "Sentence-Window": {
        "num_chunks": 115,
        "avg_chunk_len": 284.28,
    },
}

FILES = {
    "Token": RAW_DIR / "token_retrieval.csv",
    "Semantic": RAW_DIR / "semantic_retrieval.csv",
    "Sentence-Window": RAW_DIR / "sentence_window_retrieval.csv",
}


def recall_at_k(df: pd.DataFrame, k: int = TOP_K) -> float:
    """
    Compute source-level Recall@k.

    A question counts as a hit when its expected source file appears
    anywhere among the first k retrieved results.
    """
    hits = 0
    question_ids = df["question_id"].unique()

    for qid in question_ids:
        q_df = (
            df[df["question_id"] == qid]
            .sort_values("rank")
            .head(k)
        )

        expected_source = q_df["expected_source"].iloc[0]

        if expected_source in set(q_df["source_file"]):
            hits += 1

    return hits / len(question_ids)


def compute_metrics(name: str, csv_path: Path) -> dict:
    """
    Compute the required HW3 retrieval metrics for one technique.
    """
    df = pd.read_csv(csv_path)

    # Average of the rank-1 cosine similarity across all questions.
    top1_cosine = (
        df[df["rank"] == 1]
        .groupby("question_id")["cosine_sim"]
        .first()
        .mean()
    )

    # Every question has exactly top-k rows, so averaging all cosine values
    # is the overall Mean@k cosine similarity.
    mean_at_k_cosine = df["cosine_sim"].mean()

    # Retrieval latency is repeated for each rank in a question.
    # Keep one value per question before averaging.
    latency_by_question = (
        df.groupby("question_id")["retrieval_latency_ms"]
        .first()
    )
    avg_latency_ms = latency_by_question.mean()

    recall = recall_at_k(df, TOP_K)

    return {
        "Technique": name,
        "Top-1 Cosine": top1_cosine,
        f"Mean@{TOP_K} Cosine": mean_at_k_cosine,
        "# Chunks": CHUNKING_STATS[name]["num_chunks"],
        "Avg Chunk Length": CHUNKING_STATS[name]["avg_chunk_len"],
        "Avg Retrieval Latency (ms)": avg_latency_ms,
        f"Recall@{TOP_K}": recall,
    }


def main():
    rows = []

    for name, csv_path in FILES.items():
        if not csv_path.exists():
            raise FileNotFoundError(
                f"Missing retrieval file: {csv_path}. "
                "Run run_hw03_retrieval.py first."
            )

        rows.append(compute_metrics(name, csv_path))

    metrics_df = pd.DataFrame(rows)

    # Format a display copy for the terminal/report.
    display_df = metrics_df.copy()
    display_df["Top-1 Cosine"] = display_df["Top-1 Cosine"].map(lambda x: f"{x:.4f}")
    display_df[f"Mean@{TOP_K} Cosine"] = display_df[f"Mean@{TOP_K} Cosine"].map(lambda x: f"{x:.4f}")
    display_df["Avg Chunk Length"] = display_df["Avg Chunk Length"].map(lambda x: f"{x:.2f}")
    display_df["Avg Retrieval Latency (ms)"] = display_df["Avg Retrieval Latency (ms)"].map(lambda x: f"{x:.2f}")
    display_df[f"Recall@{TOP_K}"] = display_df[f"Recall@{TOP_K}"].map(lambda x: f"{x:.2f}")

    print("=" * 100)
    print("HW3 RETRIEVAL METRICS COMPARISON")
    print("=" * 100)
    print(display_df.to_string(index=False))
    print()

    # Save a Markdown table for the required METRICS.md file.
    markdown_table = display_df.to_markdown(index=False)

    content = f"""# HW3 Retrieval Metrics

The same five precommitted questions and the same
`sentence-transformers/all-MiniLM-L6-v2` embedding model were used for all
three retrieval techniques. Top-k was fixed at {TOP_K}.

{markdown_table}

## Metric definitions

- **Top-1 Cosine:** Average cosine similarity of the rank-1 result across the five questions.
- **Mean@{TOP_K} Cosine:** Average cosine similarity across all top-{TOP_K} retrieved results.
- **# Chunks:** Number of chunks/nodes created from the full three-document corpus.
- **Avg Chunk Length:** Average character length of all chunks/nodes created by that technique.
- **Avg Retrieval Latency (ms):** Mean retrieval time across the five questions, counted once per question.
- **Recall@{TOP_K}:** Fraction of questions whose expected source file appears anywhere in the top-{TOP_K} results.
"""

    METRICS_FILE.write_text(content, encoding="utf-8")

    print(f"Saved metrics table to: {METRICS_FILE}")


if __name__ == "__main__":
    main()
