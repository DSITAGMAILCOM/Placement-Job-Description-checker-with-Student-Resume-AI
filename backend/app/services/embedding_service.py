import threading
from sentence_transformers import SentenceTransformer

from app.core.config import settings

_model_lock = threading.Lock()
_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """Lazily load and cache the local 384-dim sentence-transformers model."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _model


def generate_embedding(text: str) -> list[float]:
    """Generate a normalized 384-dimensional vector embedding locally."""
    model = get_embedding_model()
    cleaned = " ".join(text.split())
    if not cleaned:
        cleaned = "empty"
    vec = model.encode(cleaned, normalize_embeddings=True)
    return vec.tolist()
