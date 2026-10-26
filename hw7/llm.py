"""Thin wrapper around the HW1 ModelClient (Ollama) for the HW7 agent loops."""

import re
import time
from typing import Any, Dict, List, Optional

from hw7 import config

_clients: Dict[tuple, Any] = {}
THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)


class ModelUnavailableError(RuntimeError):
    """Raised when the local Ollama model cannot be reached."""


def strip_think(text: str) -> str:
    """Remove any <think>...</think> block qwen3 may add."""
    return THINK_PATTERN.sub("", text or "").strip()


def get_model_client(temperature: float, seed: int) -> Any:
    """Return a HW1 ModelClient for these settings (one per setting pair)."""
    key = (config.MODEL_NAME, temperature, seed)
    if key not in _clients:
        from src.model_client import ModelClient

        client = ModelClient(
            model=config.MODEL_NAME,
            temperature=temperature,
            base_url=config.OLLAMA_URL,
        )
        # Fixed seed and a cap on reply length, set on the underlying ChatOllama.
        for name, value in (
            ("seed", seed),
            ("num_predict", config.MAX_REPLY_TOKENS),
            ("reasoning", False),
        ):
            try:
                setattr(client.model, name, value)
            except (AttributeError, ValueError):
                pass
        _clients[key] = client
    return _clients[key]


def chat(
    messages: List[Dict[str, str]],
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Call the local model; return content, token counts and latency in ms."""
    temperature = config.TEMPERATURE if temperature is None else temperature
    seed = config.SEED if seed is None else seed
    started = time.perf_counter()
    client = get_model_client(temperature, seed)
    try:
        result = client.complete(messages)
    except Exception as exc:
        raise ModelUnavailableError(f"Local model call failed: {exc}") from exc
    return {
        "content": strip_think(result["content"]),
        "input_tokens": int(result.get("input_tokens", 0)),
        "output_tokens": int(result.get("output_tokens", 0)),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }
