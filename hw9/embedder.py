# ruff: noqa: E501
"""Text embeddings for the semantic cache.

OllamaEmbedder uses nomic-embed-text (the same embedding model as HW6) through the
local Ollama server. HashEmbedder is a tiny offline stand-in used only by the
offline tests; it is never used for a reported measurement.
"""

import hashlib
import math
import re
from typing import List

import requests

from hw9 import config


def normalize(vector: List[float]) -> List[float]:
    """Scale a vector to length 1 (cosine similarity then equals the dot product)."""
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else list(vector)


class OllamaEmbedder:
    """nomic-embed-text through Ollama's /api/embed endpoint."""

    dim = config.EMBED_DIM

    def __init__(
        self, model: str = config.EMBED_MODEL, base_url: str = config.OLLAMA_URL
    ):
        """Remember the model name and the server address."""
        self.model = model
        self.base_url = base_url.rstrip("/")

    def embed(self, text: str) -> List[float]:
        """Return the unit-length embedding of one text."""
        # nomic-embed-text expects a task prefix; both sides of a comparison use the same one
        payload = {"model": self.model, "input": f"search_query: {text}"}
        reply = requests.post(f"{self.base_url}/api/embed", json=payload, timeout=60)
        reply.raise_for_status()
        return normalize(reply.json()["embeddings"][0])


class HashEmbedder:
    """Offline stand-in: hashed bag of words. Same word overlap -> higher cosine."""

    def __init__(self, dim: int = 64) -> None:
        """Choose the vector size."""
        self.dim = dim

    def embed(self, text: str) -> List[float]:
        """Return a unit-length vector built from the words of the text."""
        vector = [0.0] * self.dim
        for word in re.findall(r"[a-z0-9\-]+", text.lower()):
            digest = hashlib.md5(word.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:2], "big") % self.dim] += 1.0
        return normalize(vector)
