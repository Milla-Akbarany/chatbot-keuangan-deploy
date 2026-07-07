"""
app/services/embedding_service.py
Singleton untuk SentenceTransformer.
Model hanya dimuat SEKALI saat startup — tidak di-reload per request.
"""

from sentence_transformers import SentenceTransformer
from typing import Optional
from app.config.settings import get_settings
import logging
import time

logger = logging.getLogger(__name__)
settings = get_settings()

_model: Optional[SentenceTransformer] = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info(f"Memuat model embedding: {settings.embedding_model}")
        t0 = time.time()
        _model = SentenceTransformer(settings.embedding_model)
        logger.info(f"Model dimuat dalam {(time.time()-t0)*1000:.0f}ms")
    return _model


def embed(text: str) -> tuple[list[float], int]:
    """
    Embed satu teks.
    Return: (vector, latency_ms)
    """
    t0 = time.time()
    model = get_model()
    vector = model.encode(text, normalize_embeddings=True).tolist()
    latency_ms = int((time.time() - t0) * 1000)
    return vector, latency_ms


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed beberapa teks sekaligus — lebih efisien untuk setup/seeding."""
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return [v.tolist() for v in vectors]
