import logging
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"

model = None

def _load_model():
    global model
    if model is None:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(MODEL_NAME)
        except Exception as e:
            logger.warning(f"Failed to load embedding model: {e}. Embeddings will be unavailable.")
            model = False
    return model if model else None


def generate_embedding(text: str) -> list[float]:
    m = _load_model()
    if m is None:
        logger.warning("Embedding model not available, returning mock embedding")
        return [0.0] * 384

    embedding = m.encode(
        text,
        normalize_embeddings=True,
    )

    return embedding.tolist()


def embed_document_chunks(
    db: Session,
    document_id: int,
) -> int:
    m = _load_model()
    if m is None:
        logger.warning("Embedding model not available, skipping embeddings")
        return 0

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    for chunk in chunks:
        chunk.embedding = generate_embedding(chunk.content)

    db.commit()

    return len(chunks)