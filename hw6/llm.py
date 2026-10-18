"""Thin wrapper around the HW1 ModelClient (Ollama qwen3:8b) and the embedding model."""
import re
import time
from typing import Any, Dict, List, Optional

from hw6 import config

_model_client: Optional[Any] = None
_embedder: Optional[Any] = None
THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)


class ModelUnavailableError(RuntimeError):
    """Raised when the local Ollama model or embedder cannot be reached."""


def strip_think(text: str) -> str:
    """Remove any <think>...</think> block qwen3 may add."""
    return THINK_PATTERN.sub("", text or "").strip()


def get_model_client() -> Any:
    """Return the shared HW1 ModelClient, creating it on first use."""
    global _model_client
    if _model_client is None:
        from src.model_client import ModelClient

        client = ModelClient(
            model=config.MODEL_NAME,
            temperature=0.0,
            base_url=config.OLLAMA_URL,
        )
        # Reproducibility: fixed seed and a cap on reply length.
        for name, value in (("seed", config.SEED), ("num_predict", config.MAX_REPLY_TOKENS), ("reasoning", False)):
            try:
                setattr(client.model, name, value)
            except (AttributeError, ValueError):
                pass
        _model_client = client
    return _model_client


def chat(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Call the local model and return content, token counts and latency in ms."""
    started = time.perf_counter()
    client = get_model_client()
    input_tokens = output_tokens = 0
    content = ""
    for attempt, budget in enumerate((config.MAX_REPLY_TOKENS, config.MAX_REPLY_TOKENS * 4)):
        try:
            setattr(client.model, "num_predict", budget)
        except (AttributeError, ValueError):
            pass
        try:
            result = client.complete(messages)
        except Exception as exc:
            raise ModelUnavailableError(f"Local model call failed: {exc}") from exc
        input_tokens += int(result.get("input_tokens", 0))
        output_tokens += int(result.get("output_tokens", 0))
        content = strip_think(result["content"])
        if content:
            break
    try:
        setattr(client.model, "num_predict", config.MAX_REPLY_TOKENS)
    except (AttributeError, ValueError):
        pass
    return {
        "content": content,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def embed(text: str) -> List[float]:
    """Return the nomic-embed-text vector for one piece of text."""
    global _embedder
    try:
        if _embedder is None:
            from langchain_ollama import OllamaEmbeddings

            _embedder = OllamaEmbeddings(
                model=config.EMBEDDING_MODEL,
                base_url=config.OLLAMA_URL,
            )
        vector = _embedder.embed_query(text)
    except Exception as exc:
        raise ModelUnavailableError(f"Embedding call failed: {exc}") from exc
    return [float(value) for value in vector]
