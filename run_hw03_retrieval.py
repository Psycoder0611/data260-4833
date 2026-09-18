"""
DATA 260 - Homework 3
Part 2: LlamaIndex Retrieval Comparison

Step 1:
Load the ClinicalTrials.gov PDF corpus and verify that
text can be extracted successfully from every document.
"""

from pathlib import Path
from pypdf import PdfReader
from llama_index.core import Document
from llama_index.core.node_parser import TokenTextSplitter
import csv
import yaml
import numpy as np
from llama_index.core.node_parser import SemanticSplitterNodeParser

from llama_index.core import VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.node_parser import SentenceWindowNodeParser
import time

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

CORPUS_DIR = Path("data/hw03")
QUESTIONS_FILE = Path("reports/hw03/questions.yaml")
RAW_DIR = Path("reports/hw03/raw")

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 3

# ---------------------------------------------------------
# PDF loading helper
# ---------------------------------------------------------

def extract_pdf_text(pdf_path: Path) -> str:
    """
    Extract text from every page of one PDF file.
    """
    reader = PdfReader(pdf_path)

    pages = []

    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)

    return "\n".join(pages)

#added new for TokenTextSplitter
def run_token_chunking(pdf_files):
    """
    Chunk the corpus using LlamaIndex TokenTextSplitter.
    """

    print()
    print("=" * 70)
    print("TOKEN TEXT SPLITTER")
    print("=" * 70)

    documents = []

    # Convert each PDF into a LlamaIndex Document
    for pdf_path in pdf_files:
        text = extract_pdf_text(pdf_path)

        documents.append(
            Document(
                text=text,
                metadata={
                    "source_file": pdf_path.name
                }
            )
        )

    # Token-based chunking configuration
    splitter = TokenTextSplitter(
        chunk_size=512,
        chunk_overlap=50
    )

    nodes = splitter.get_nodes_from_documents(documents)

    chunk_lengths = [len(node.text) for node in nodes]

    print("Chunk size: 512 tokens")
    print("Chunk overlap: 50 tokens")
    print(f"Total chunks created: {len(nodes)}")
    print(
        f"Average chunk length: "
        f"{sum(chunk_lengths) / len(chunk_lengths):.2f} characters"
    )

    print()
    print("First chunk preview:")
    print(nodes[0].text[:300].replace("\n", " "))

    print()
    print("First chunk source:")
    print(nodes[0].metadata.get("source_file"))

    return nodes

#cosine-similarity helper
def cosine_similarity(vec_a, vec_b):
    """
    Compute cosine similarity between two embedding vectors.
    """

    a = np.array(vec_a, dtype=float)
    b = np.array(vec_b, dtype=float)

    denominator = np.linalg.norm(a) * np.linalg.norm(b)

    if denominator == 0:
        return 0.0

    return float(np.dot(a, b) / denominator)


#retrieval function
def run_token_retrieval(token_nodes, embed_model):
    """
    Build a VectorStoreIndex from TokenTextSplitter chunks
    and retrieve the top-k chunks for each predefined question.
    """

    print()
    print("=" * 70)
    print("TOKEN-BASED RETRIEVAL")
    print("=" * 70)

    # Load the fixed questions created before retrieval.
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        question_data = yaml.safe_load(f)

    questions = question_data["questions"]

    # Public sentence-transformer embedding model required for HW3.
    # embed_model = HuggingFaceEmbedding(
    #     model_name=EMBEDDING_MODEL
    # ) #because I'm now creating the embedding model once inside main() & passing it into the func

    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"Top-k retrieval: {TOP_K}")

    # Create in-memory vector index from token chunks.
    index = VectorStoreIndex(
        token_nodes,
        embed_model=embed_model
    )

    retriever = index.as_retriever(
        similarity_top_k=TOP_K
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    output_file = RAW_DIR / "token_retrieval.csv"

    rows = []

    for item in questions:

        question_id = item["id"]
        question = item["question"]
        expected_source = item["expected_source"]

        print()
        print("-" * 70)
        print(f"{question_id}: {question}")

        # Query embedding
        query_embedding = embed_model.get_query_embedding(question)

        print(f"Query embedding dimension: {len(query_embedding)}")
        print(
            "First 8 query embedding values:",
            [round(x, 6) for x in query_embedding[:8]]
        )

        # Retrieve top-k nodes
        # results = retriever.retrieve(question)   removed in sec 2.6 for timing support for all retrieval sections
        start_time = time.perf_counter()

        results = retriever.retrieve(question)

        retrieval_latency_ms = (
            time.perf_counter() - start_time
        ) * 1000


        # Explicitly calculate document embeddings for shape verification.
        doc_embeddings = [
            embed_model.get_text_embedding(result.node.get_content())
            for result in results
        ]

        stacked_docs = np.array(doc_embeddings)

        print(f"Query vector shape: {np.array(query_embedding).shape}")
        print(f"Stacked document vector shape: {stacked_docs.shape}")
        print(f"Retrieval latency: {retrieval_latency_ms:.2f} ms")

        for rank, result in enumerate(results, start=1):

            text = result.node.get_content()

            document_embedding = doc_embeddings[rank - 1]

            cosine_sim = cosine_similarity(
                query_embedding,
                document_embedding
            )

            source_file = result.node.metadata.get(
                "source_file",
                "unknown"
            )

            preview = " ".join(
                text[:160].split()
            )

            print()
            print(f"Rank {rank}")
            print(f"Source: {source_file}")
            print(f"Store score: {result.score:.6f}")
            print(f"Cosine similarity: {cosine_sim:.6f}")
            print(f"Chunk length: {len(text)}")
            print(f"Preview: {preview}")

            rows.append({
                "question_id": question_id,
                "question": question,
                "expected_source": expected_source,
                "rank": rank,
                "source_file": source_file,
                "store_score": result.score,
                "cosine_sim": cosine_sim,
                "chunk_len": len(text),
                "retrieval_latency_ms": retrieval_latency_ms,
                "preview": preview
            })

    # Save machine-readable retrieval output.
    with open(output_file, "w", newline="", encoding="utf-8") as f:

        fieldnames = [
            "question_id",
            "question",
            "expected_source",
            "rank",
            "source_file",
            "store_score",
            "cosine_sim",
            "chunk_len",
            "retrieval_latency_ms",
            "preview"
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)

    print()
    print("=" * 70)
    print(f"Saved token retrieval results to: {output_file}")
    print("=" * 70)

    return rows

#added for sec 2.4 semantic chunking
def run_semantic_chunking(pdf_files, embed_model):
    """
    Chunk the corpus using LlamaIndex SemanticSplitterNodeParser.
    """

    print()
    print("=" * 70)
    print("SEMANTIC SPLITTER")
    print("=" * 70)

    documents = []

    for pdf_path in pdf_files:
        text = extract_pdf_text(pdf_path)

        documents.append(
            Document(
                text=text,
                metadata={
                    "source_file": pdf_path.name
                }
            )
        )

    # Semantic chunking groups sentences based on embedding similarity.
    splitter = SemanticSplitterNodeParser(
        buffer_size=1,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model
    )

    nodes = splitter.get_nodes_from_documents(documents)

    chunk_lengths = [len(node.text) for node in nodes]

    print("Buffer size: 1")
    print("Breakpoint percentile threshold: 95")
    print(f"Total chunks created: {len(nodes)}")
    print(
        f"Average chunk length: "
        f"{sum(chunk_lengths) / len(chunk_lengths):.2f} characters"
    )

    print()
    print("First chunk preview:")
    print(nodes[0].text[:300].replace("\n", " "))

    print()
    print("First chunk source:")
    print(nodes[0].metadata.get("source_file"))

    return nodes


#sec 2.4 Sentence Chunking
# Clarification: this function performs semantic retrieval for Section 2.4.
def run_semantic_retrieval(semantic_nodes, embed_model):
    """
    Build a VectorStoreIndex from semantic chunks
    and retrieve the top-k chunks for each predefined question.
    """

    print()
    print("=" * 70)
    print("SEMANTIC-BASED RETRIEVAL")
    print("=" * 70)

    # Load the fixed questions created before retrieval.
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        question_data = yaml.safe_load(f)

    questions = question_data["questions"]

    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"Top-k retrieval: {TOP_K}")

    # Create in-memory vector index from semantic chunks.
    index = VectorStoreIndex(
        semantic_nodes,
        embed_model=embed_model
    )

    retriever = index.as_retriever(
        similarity_top_k=TOP_K
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    output_file = RAW_DIR / "semantic_retrieval.csv"

    rows = []

    for item in questions:

        question_id = item["id"]
        question = item["question"]
        expected_source = item["expected_source"]

        print()
        print("-" * 70)
        print(f"{question_id}: {question}")

        # Query embedding
        query_embedding = embed_model.get_query_embedding(question)

        print(f"Query embedding dimension: {len(query_embedding)}")
        print(
            "First 8 query embedding values:",
            [round(x, 6) for x in query_embedding[:8]]
        )

        # Retrieve top-k semantic chunks
        # results = retriever.retrieve(question)
        start_time = time.perf_counter()

        results = retriever.retrieve(question)

        retrieval_latency_ms = (
            time.perf_counter() - start_time
        ) * 1000

        # Explicit document embeddings for cosine-similarity verification.
        doc_embeddings = [
            embed_model.get_text_embedding(result.node.get_content())
            for result in results
        ]

        stacked_docs = np.array(doc_embeddings)

        print(f"Query vector shape: {np.array(query_embedding).shape}")
        print(f"Stacked document vector shape: {stacked_docs.shape}")
        print(f"Retrieval latency: {retrieval_latency_ms:.2f} ms")

        for rank, result in enumerate(results, start=1):

            text = result.node.get_content()

            document_embedding = doc_embeddings[rank - 1]

            cosine_sim = cosine_similarity(
                query_embedding,
                document_embedding
            )

            source_file = result.node.metadata.get(
                "source_file",
                "unknown"
            )

            preview = " ".join(
                text[:160].split()
            )

            print()
            print(f"Rank {rank}")
            print(f"Source: {source_file}")
            print(f"Store score: {result.score:.6f}")
            print(f"Cosine similarity: {cosine_sim:.6f}")
            print(f"Chunk length: {len(text)}")
            print(f"Preview: {preview}")

            rows.append({
                "question_id": question_id,
                "question": question,
                "expected_source": expected_source,
                "rank": rank,
                "source_file": source_file,
                "store_score": result.score,
                "cosine_sim": cosine_sim,
                "chunk_len": len(text),
                "retrieval_latency_ms": retrieval_latency_ms,
                "preview": preview
            })

    # Save machine-readable semantic retrieval results.
    with open(output_file, "w", newline="", encoding="utf-8") as f:

        fieldnames = [
            "question_id",
            "question",
            "expected_source",
            "rank",
            "source_file",
            "store_score",
            "cosine_sim",
            "chunk_len",
            "retrieval_latency_ms",
            "preview"
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)

    print()
    print("=" * 70)
    print(f"Saved semantic retrieval results to: {output_file}")
    print("=" * 70)

    return rows


#sec 2.5:Sentence-Window Chunking
def run_sentence_window_chunking(pdf_files):
    """
    Chunk the corpus using LlamaIndex SentenceWindowNodeParser.

    Each node contains one sentence, while neighboring sentences
    are preserved in metadata as a context window.
    """

    print()
    print("=" * 70)
    print("SENTENCE-WINDOW SPLITTER")
    print("=" * 70)

    documents = []

    for pdf_path in pdf_files:
        text = extract_pdf_text(pdf_path)

        documents.append(
            Document(
                text=text,
                metadata={
                    "source_file": pdf_path.name
                }
            )
        )

    # Each node contains a single sentence.
    # Neighboring sentences are stored in the "window" metadata field.
    splitter = SentenceWindowNodeParser.from_defaults(
        window_size=3,
        window_metadata_key="window",
        original_text_metadata_key="original_sentence"
    )

    nodes = splitter.get_nodes_from_documents(documents)

    chunk_lengths = [len(node.text) for node in nodes]

    print("Window size: 3 neighboring sentences")
    print("Node content: 1 sentence")
    print(f"Total sentence nodes created: {len(nodes)}")
    print(
        f"Average sentence length: "
        f"{sum(chunk_lengths) / len(chunk_lengths):.2f} characters"
    )

    print()
    print("First sentence node:")
    print(nodes[0].text[:300].replace("\n", " "))

    print()
    print("First sentence source:")
    print(nodes[0].metadata.get("source_file"))

    print()
    print("First sentence window metadata:")
    print(
        nodes[0].metadata.get(
            "window",
            ""
        )[:500].replace("\n", " ")
    )

    return nodes


#sentence-window retrieval
# Section 2.5 retrieval using the sentence-window nodes.
def run_sentence_window_retrieval(sentence_nodes, embed_model):
    """
    Build a VectorStoreIndex from sentence-window nodes
    and retrieve the top-k results for each predefined question.
    """

    print()
    print("=" * 70)
    print("SENTENCE-WINDOW RETRIEVAL")
    print("=" * 70)

    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        question_data = yaml.safe_load(f)

    questions = question_data["questions"]

    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"Top-k retrieval: {TOP_K}")

    index = VectorStoreIndex(
        sentence_nodes,
        embed_model=embed_model
    )

    retriever = index.as_retriever(
        similarity_top_k=TOP_K
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    output_file = RAW_DIR / "sentence_window_retrieval.csv"

    rows = []

    for item in questions:

        question_id = item["id"]
        question = item["question"]
        expected_source = item["expected_source"]

        print()
        print("-" * 70)
        print(f"{question_id}: {question}")

        query_embedding = embed_model.get_query_embedding(question)

        print(f"Query embedding dimension: {len(query_embedding)}")
        print(
            "First 8 query embedding values:",
            [round(x, 6) for x in query_embedding[:8]]
        )

        # results = retriever.retrieve(question)
        start_time = time.perf_counter()

        results = retriever.retrieve(question)

        retrieval_latency_ms = (
            time.perf_counter() - start_time
        ) * 1000

        doc_embeddings = [
            embed_model.get_text_embedding(result.node.get_content())
            for result in results
        ]

        stacked_docs = np.array(doc_embeddings)

        print(f"Query vector shape: {np.array(query_embedding).shape}")
        print(f"Stacked document vector shape: {stacked_docs.shape}")
        print(f"Retrieval latency: {retrieval_latency_ms:.2f} ms")

        for rank, result in enumerate(results, start=1):

            text = result.node.get_content()
            document_embedding = doc_embeddings[rank - 1]

            cosine_sim = cosine_similarity(
                query_embedding,
                document_embedding
            )

            source_file = result.node.metadata.get(
                "source_file",
                "unknown"
            )

            window_text = result.node.metadata.get(
                "window",
                text
            )

            preview = " ".join(
                window_text[:160].split()
            )

            print()
            print(f"Rank {rank}")
            print(f"Source: {source_file}")
            print(f"Store score: {result.score:.6f}")
            print(f"Cosine similarity: {cosine_sim:.6f}")
            print(f"Sentence length: {len(text)}")
            print(f"Window length: {len(window_text)}")
            print(f"Window preview: {preview}")

            rows.append({
                "question_id": question_id,
                "question": question,
                "expected_source": expected_source,
                "rank": rank,
                "source_file": source_file,
                "store_score": result.score,
                "cosine_sim": cosine_sim,
                "chunk_len": len(text),
                "window_len": len(window_text),
                "retrieval_latency_ms": retrieval_latency_ms,
                "preview": preview
            })

    with open(output_file, "w", newline="", encoding="utf-8") as f:

        fieldnames = [
            "question_id",
            "question",
            "expected_source",
            "rank",
            "source_file",
            "store_score",
            "cosine_sim",
            "chunk_len",
            "window_len",
            "retrieval_latency_ms",
            "preview"
        ]

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(rows)

    print()
    print("=" * 70)
    print(f"Saved sentence-window retrieval results to: {output_file}")
    print("=" * 70)

    return rows

# ---------------------------------------------------------
# Main corpus check
# ---------------------------------------------------------

def main():

    pdf_files = sorted(CORPUS_DIR.glob("*.pdf"))

    print("=" * 70)
    print("HW3 CORPUS LOADING CHECK")
    print("=" * 70)

    print(f"Corpus directory: {CORPUS_DIR}")
    print(f"PDF files found: {len(pdf_files)}")
    print()

    if not pdf_files:
        raise FileNotFoundError(
            f"No PDF files found in {CORPUS_DIR}"
        )

    total_characters = 0

    for pdf_path in pdf_files:

        text = extract_pdf_text(pdf_path)

        total_characters += len(text)

        print(f"File: {pdf_path.name}")
        print(f"Extracted characters: {len(text):,}")

        # Print a small preview so we know meaningful text was extracted.
        preview = " ".join(text[:200].split())

        print(f"Preview: {preview}")
        print("-" * 70)

    print()
    print(f"Total extracted characters: {total_characters:,}")
    print("Corpus loading completed successfully.")

    # Load the embedding model once
    embed_model = HuggingFaceEmbedding(
        model_name=EMBEDDING_MODEL
    )

    # Run the first required chunking technique
    token_nodes = run_token_chunking(pdf_files)

    # Run retrieval over the token-based chunks
    run_token_retrieval(token_nodes,embed_model)

    # Run semantic chunking
    semantic_nodes = run_semantic_chunking(
    pdf_files,
    embed_model
    )

    # Semantic retrieval
    run_semantic_retrieval(
        semantic_nodes,
        embed_model
    )

# Sentence-window chunking
    sentence_window_nodes = run_sentence_window_chunking(
        pdf_files
    )

    run_sentence_window_retrieval(
        sentence_window_nodes,
        embed_model
    )

if __name__ == "__main__":
    main()