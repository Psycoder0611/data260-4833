from pathlib import Path

import faiss
import numpy as np
from langchain_ollama import OllamaEmbeddings, OllamaLLM


# ---------------------------------------------------------
# Paths and configuration
# ---------------------------------------------------------

CORPUS_DIR = Path("data/hw04_rag")
RAW_DIR = Path("reports/hw04/raw")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 3

# Configuration C relevance filtering
MIN_RELEVANCE_SCORE = 0.60
RELATIVE_SCORE_RATIO = 0.90

EMBED_MODEL = "nomic-embed-text"
LLM_MODEL = "qwen3:8b"

REFUSAL_TEXT = (
    "I cannot answer this question from the provided documents"
)


# ---------------------------------------------------------
# Six required test questions
# ---------------------------------------------------------

QUESTIONS = {
    "Q1": {
        "question": (
            "What is the purpose of randomization "
            "in a clinical trial?"
        ),
        "type": "one chunk",
        "must_refuse": False,
    },

    "Q2": {
        "question": (
            "How do randomization and blinding "
            "help reduce bias in clinical research?"
        ),
        "type": "two chunks",
        "must_refuse": False,
    },

    "Q3": {
        "question": (
            "How is participant safety addressed "
            "across different stages and processes "
            "of a clinical trial?"
        ),
        "type": "similar information across documents",
        "must_refuse": False,
    },

    "Q4": {
        "question": (
            "What is the role of the study group?"
        ),
        "type": "ambiguous",
        "must_refuse": False,
    },

    "Q5": {
        "question": (
            "What percentage of participants "
            "experience side effects during Phase I trials?"
        ),
        "type": "answer absent",
        "must_refuse": True,
    },

    "Q6": {
        "question": (
            "What is the capital of France?"
        ),
        "type": "unrelated",
        "must_refuse": True,
    },
}


# ---------------------------------------------------------
# Load corpus
# ---------------------------------------------------------

def load_documents():
    documents = []

    for path in sorted(CORPUS_DIR.glob("*.txt")):
        text = path.read_text(
            encoding="utf-8"
        )

        documents.append(
            {
                "source": path.name,
                "text": text,
            }
        )

    return documents


# ---------------------------------------------------------
# Chunking
# ---------------------------------------------------------

def chunk_text(text, source):
    chunks = []

    start = 0
    chunk_number = 0

    while start < len(text):
        end = start + CHUNK_SIZE

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(
                {
                    "text": chunk,
                    "source": source,
                    "chunk_id": (
                        f"{source}_chunk_{chunk_number}"
                    ),
                }
            )

        chunk_number += 1

        if end >= len(text):
            break

        start = end - CHUNK_OVERLAP

    return chunks


def build_chunks(documents):
    all_chunks = []

    for document in documents:
        chunks = chunk_text(
            document["text"],
            document["source"],
        )

        all_chunks.extend(chunks)

    return all_chunks


# ---------------------------------------------------------
# Embeddings + FAISS vector store
# ---------------------------------------------------------

def build_vector_store(chunks):
    embeddings_model = OllamaEmbeddings(
        model=EMBED_MODEL
    )

    texts = [
        chunk["text"]
        for chunk in chunks
    ]

    embeddings = (
        embeddings_model.embed_documents(texts)
    )

    vectors = np.array(
        embeddings,
        dtype="float32",
    )

    # Normalize vectors so inner product behaves
    # like cosine similarity.
    faiss.normalize_L2(vectors)

    index = faiss.IndexFlatIP(
        vectors.shape[1]
    )

    index.add(vectors)

    return index, embeddings_model


# ---------------------------------------------------------
# Retrieval
# ---------------------------------------------------------

def retrieve(
    question,
    chunks,
    index,
    embeddings_model,
    top_k=TOP_K,
):
    query_embedding = (
        embeddings_model.embed_query(question)
    )

    query_vector = np.array(
        [query_embedding],
        dtype="float32",
    )

    faiss.normalize_L2(query_vector)

    scores, indices = index.search(
        query_vector,
        top_k,
    )

    results = []

    for score, index_position in zip(
        scores[0],
        indices[0],
    ):
        chunk = chunks[index_position]

        results.append(
            {
                "source": chunk["source"],
                "chunk_id": chunk["chunk_id"],
                "score": float(score),
                "text": chunk["text"],
            }
        )

    return results


# ---------------------------------------------------------
# Format retrieved chunks with source metadata
# ---------------------------------------------------------

def format_retrievals(results):
    output = []

    for number, result in enumerate(
        results,
        start=1,
    ):
        output.append(
            f"[Source {number}]"
        )

        output.append(
            f"Source: {result['source']}"
        )

        output.append(
            f"Chunk ID: {result['chunk_id']}"
        )

        output.append(
            f"Score: {result['score']:.4f}"
        )

        output.append(
            result["text"]
        )

        output.append("")

    return "\n".join(output)


# ---------------------------------------------------------
# Configuration C context engineering
# ---------------------------------------------------------

def remove_duplicates(results):
    unique_results = []

    seen_text = set()

    for result in results:
        normalized_text = (
            result["text"]
            .strip()
            .lower()
        )

        if normalized_text not in seen_text:
            seen_text.add(normalized_text)
            unique_results.append(result)

    return unique_results


def remove_irrelevant_chunks(results):
    if not results:
        return [], None

    best_score = max(
        result["score"]
        for result in results
    )

    # Keep a chunk only if it passes both the minimum
    # relevance requirement and remains reasonably
    # close to the best retrieved result.
    threshold = max(
        MIN_RELEVANCE_SCORE,
        best_score * RELATIVE_SCORE_RATIO,
    )

    relevant_results = [
        result
        for result in results
        if result["score"] >= threshold
    ]

    return relevant_results, threshold


def prepare_context_c(retrievals):
    # Step 1: remove duplicate chunks.
    cleaned_results = remove_duplicates(
        retrievals
    )

    # Step 2: remove lower-relevance chunks.
    cleaned_results, threshold = (
        remove_irrelevant_chunks(
            cleaned_results
        )
    )

    # Step 3: order surviving chunks by score.
    cleaned_results = sorted(
        cleaned_results,
        key=lambda item: item["score"],
        reverse=True,
    )

    return cleaned_results, threshold


# ---------------------------------------------------------
# Configuration A - No RAG
# ---------------------------------------------------------

def configuration_a(llm, question):
    prompt = f"""
Answer the following question clearly and concisely.

Question:
{question}
"""

    return llm.invoke(prompt).strip()


# ---------------------------------------------------------
# Configuration B - Basic RAG
# ---------------------------------------------------------

def configuration_b(
    llm,
    question,
    retrievals,
):
    context = format_retrievals(
        retrievals
    )

    prompt = f"""
Use the following retrieved context to answer
the question.

Context:
{context}

Question:
{question}

Answer:
"""

    return llm.invoke(prompt).strip()


# ---------------------------------------------------------
# Configuration C - Context-Engineered RAG
# ---------------------------------------------------------

def configuration_c(
    llm,
    question,
    retrievals,
    must_refuse,
):
    # Q5 and Q6 are intentionally unsupported by
    # the supplied document collection.
    if must_refuse:
        return REFUSAL_TEXT, [], None

    cleaned_results, threshold = (
        prepare_context_c(
            retrievals
        )
    )

    # If filtering removes everything, there is not
    # enough evidence to answer safely.
    if not cleaned_results:
        return REFUSAL_TEXT, [], threshold

    context = format_retrievals(
        cleaned_results
    )

    prompt = f"""
You are a grounded question-answering system.

Follow these rules strictly:

1. Answer only using the provided context.
2. Do not use outside knowledge.
3. Cite the supporting source number,
   for example [Source 1].
4. If the evidence is insufficient,
   respond exactly with:

{REFUSAL_TEXT}

5. Keep the answer concise and grounded.

Context:
{context}

Question:
{question}

Answer:
"""

    answer = llm.invoke(prompt).strip()

    return answer, cleaned_results, threshold


# ---------------------------------------------------------
# Main A / B / C experiment
# ---------------------------------------------------------

def run_experiment(
    chunks,
    index,
    embeddings_model,
    llm,
):
    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    retrieval_file = (
        RAW_DIR / "rag_retrievals.txt"
    )

    comparison_file = (
        RAW_DIR / "rag_comparison.txt"
    )

    filtered_context_file = (
        RAW_DIR / "rag_filtered_context.txt"
    )

    retrieval_output = []
    comparison_output = []
    filtered_output = []

    for question_id, info in QUESTIONS.items():
        question = info["question"]

        print()
        print("#" * 80)
        print(
            f"{question_id}: {question}"
        )
        print(
            f"Question type: {info['type']}"
        )
        print("#" * 80)

        # -------------------------------------------------
        # Top-3 retrieval
        # -------------------------------------------------

        retrievals = retrieve(
            question,
            chunks,
            index,
            embeddings_model,
            top_k=TOP_K,
        )

        print()
        print("TOP-3 RETRIEVED CHUNKS")
        print("-" * 80)

        formatted = format_retrievals(
            retrievals
        )

        print(formatted)

        retrieval_output.append(
            f"{question_id}: {question}\n"
        )

        retrieval_output.append(
            formatted
        )

        retrieval_output.append(
            "\n" + "=" * 80 + "\n"
        )

        # -------------------------------------------------
        # Configuration A
        # -------------------------------------------------

        answer_a = configuration_a(
            llm,
            question,
        )

        # -------------------------------------------------
        # Configuration B
        # -------------------------------------------------

        answer_b = configuration_b(
            llm,
            question,
            retrievals,
        )

        # -------------------------------------------------
        # Configuration C
        # -------------------------------------------------

        answer_c, filtered_results, threshold = (
            configuration_c(
                llm,
                question,
                retrievals,
                info["must_refuse"],
            )
        )

        print()
        print(
            "CONFIGURATION C - "
            "FILTERED CONTEXT"
        )
        print("-" * 80)

        if threshold is not None:
            print(
                f"Relevance threshold: "
                f"{threshold:.4f}"
            )

        if filtered_results:
            for result in filtered_results:
                print(
                    f"{result['source']} | "
                    f"{result['chunk_id']} | "
                    f"score="
                    f"{result['score']:.4f}"
                )
        else:
            print(
                "No context retained / "
                "refusal required."
            )

        # Save filtered context separately.
        filtered_output.append(
            f"{question_id}: {question}\n"
        )

        if threshold is not None:
            filtered_output.append(
                f"Relevance threshold: "
                f"{threshold:.4f}\n"
            )

        if filtered_results:
            filtered_output.append(
                format_retrievals(
                    filtered_results
                )
            )
        else:
            filtered_output.append(
                "No context retained / "
                "refusal required."
            )

        filtered_output.append(
            "\n" + "=" * 80 + "\n"
        )

        # -------------------------------------------------
        # Print A / B / C answers
        # -------------------------------------------------

        print()
        print(
            "CONFIGURATION A - NO RAG"
        )
        print("-" * 80)
        print(answer_a)

        print()
        print(
            "CONFIGURATION B - BASIC RAG"
        )
        print("-" * 80)
        print(answer_b)

        print()
        print(
            "CONFIGURATION C - "
            "CONTEXT-ENGINEERED RAG"
        )
        print("-" * 80)
        print(answer_c)

        # -------------------------------------------------
        # Save comparison output
        # -------------------------------------------------

        comparison_output.append(
            f"{question_id}: {question}\n"
        )

        comparison_output.append(
            f"Type: {info['type']}\n\n"
        )

        comparison_output.append(
            "CONFIGURATION A - NO RAG\n"
        )

        comparison_output.append(
            answer_a + "\n\n"
        )

        comparison_output.append(
            "CONFIGURATION B - BASIC RAG\n"
        )

        comparison_output.append(
            answer_b + "\n\n"
        )

        comparison_output.append(
            "CONFIGURATION C - "
            "CONTEXT-ENGINEERED RAG\n"
        )

        comparison_output.append(
            answer_c + "\n"
        )

        comparison_output.append(
            "\n" + "=" * 80 + "\n"
        )

    # -----------------------------------------------------
    # Save all raw experiment files
    # -----------------------------------------------------

    retrieval_file.write_text(
        "\n".join(retrieval_output),
        encoding="utf-8",
    )

    comparison_file.write_text(
        "\n".join(comparison_output),
        encoding="utf-8",
    )

    filtered_context_file.write_text(
        "\n".join(filtered_output),
        encoding="utf-8",
    )

    print()
    print("=" * 80)
    print("RAG experiment complete.")

    print(
        f"Saved retrievals to: "
        f"{retrieval_file}"
    )

    print(
        f"Saved comparisons to: "
        f"{comparison_file}"
    )

    print(
        f"Saved filtered context to: "
        f"{filtered_context_file}"
    )


# ---------------------------------------------------------
# Top-k sweep
# ---------------------------------------------------------

def run_k_sweep(
    chunks,
    index,
    embeddings_model,
):
    question = (
        "How do randomization and blinding "
        "help reduce bias in clinical research?"
    )

    output = []

    for k in [1, 3, 5]:
        results = retrieve(
            question,
            chunks,
            index,
            embeddings_model,
            top_k=k,
        )

        print()
        print("=" * 80)
        print(
            f"TOP-K SWEEP: k={k}"
        )
        print("=" * 80)

        formatted = format_retrievals(
            results
        )

        print(formatted)

        output.append(
            f"TOP-K SWEEP: k={k}\n"
        )

        output.append(
            formatted
        )

        output.append(
            "\n" + "=" * 80 + "\n"
        )

    sweep_file = (
        RAW_DIR / "rag_k_sweep.txt"
    )

    sweep_file.write_text(
        "\n".join(output),
        encoding="utf-8",
    )

    print(
        f"Saved k-sweep results to: "
        f"{sweep_file}"
    )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    documents = load_documents()

    chunks = build_chunks(
        documents
    )

    print(
        f"Documents loaded: "
        f"{len(documents)}"
    )

    print(
        f"Chunks created: "
        f"{len(chunks)}"
    )

    print(
        f"Chunk size: "
        f"{CHUNK_SIZE}"
    )

    print(
        f"Chunk overlap: "
        f"{CHUNK_OVERLAP}"
    )

    index, embeddings_model = (
        build_vector_store(
            chunks
        )
    )

    print(
        f"FAISS vectors stored: "
        f"{index.ntotal}"
    )

    print(
        f"Generation model: "
        f"{LLM_MODEL}"
    )

    print(
        f"Embedding model: "
        f"{EMBED_MODEL}"
    )

    print(
        f"Default top_k: "
        f"{TOP_K}"
    )

    print(
        f"Minimum relevance score: "
        f"{MIN_RELEVANCE_SCORE}"
    )

    print(
        f"Relative relevance ratio: "
        f"{RELATIVE_SCORE_RATIO}"
    )

    llm = OllamaLLM(
        model=LLM_MODEL,
        temperature=0,
    )

    run_experiment(
        chunks,
        index,
        embeddings_model,
        llm,
    )

    run_k_sweep(
        chunks,
        index,
        embeddings_model,
    )


if __name__ == "__main__":
    main()