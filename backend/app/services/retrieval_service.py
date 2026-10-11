from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.embedding_service import generate_embedding


import time
import logging

logger = logging.getLogger(__name__)

DEFAULT_DISTANCE_THRESHOLD = 0.80


def search_similar_chunks(
    db: Session,
    query: str,
    limit: int = 5,
    distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
    document_ids: list[int] | None = None,
    user_id: int | None = None,
    query_embedding: list[float] | None = None,
):
    start_time = time.perf_counter()
    if query_embedding is None:
        emb_start = time.perf_counter()
        query_embedding = generate_embedding(query)
        logger.info(f"[TIMING:embedding] generated in {(time.perf_counter() - emb_start)*1000:.2f}ms")

    # ---------------------------------------------------------
    # [DIAG] Log every input to this function
    # ---------------------------------------------------------
    print(f"[DIAG:retrieval] query={query!r}")
    print(f"[DIAG:retrieval] embedding dim={len(query_embedding)}")
    print(f"[DIAG:retrieval] embedding[:3]={query_embedding[:3]}")
    print(f"[DIAG:retrieval] distance_threshold={distance_threshold}")
    print(f"[DIAG:retrieval] limit={limit}")
    print(f"[DIAG:retrieval] document_ids received = {document_ids!r}")
    print(f"[DIAG:retrieval] document_ids type = {type(document_ids).__name__}")
    if document_ids is not None:
        print(f"[DIAG:retrieval] document_ids element types = {[type(x).__name__ for x in document_ids]}")

    # ---------------------------------------------------------
    # Optional document filtering
    #
    # None    -> search the entire document library
    # [1, 3]  -> search only documents 1 and 3
    # ---------------------------------------------------------

    document_filter = ""
    base_params = {
        "query_embedding": str(query_embedding),
        "limit": limit,
    }

    if document_ids is not None:
        if not document_ids:
            print("[DIAG:retrieval] ⚠ document_ids is empty list → returning []")
            return []

        document_filter += """
          AND document_chunks.document_id = ANY(:document_ids)
        """

        base_params["document_ids"] = document_ids

    if user_id is not None:
        document_filter += """
          AND documents.user_id = :user_id
        """
        base_params["user_id"] = user_id

    print(f"[DIAG:retrieval] document_filter applied = {bool(document_filter)}")
    print(f"[DIAG:retrieval] base_params keys = {list(base_params.keys())}")
    print(f"[DIAG:retrieval] base_params['document_ids'] = {base_params.get('document_ids')!r}")

    # ---------------------------------------------------------
    # [DIAG] Run WITHOUT the threshold first to see raw distances
    # ---------------------------------------------------------
    sql_no_threshold = text(f"""
        SELECT
            document_chunks.id,
            document_chunks.document_id,
            document_chunks.chunk_index,
            document_chunks.embedding <=> CAST(:query_embedding AS vector) AS distance
        FROM document_chunks
        { "JOIN documents ON documents.id = document_chunks.document_id" if user_id is not None else "" }
        WHERE document_chunks.embedding IS NOT NULL
          {document_filter}
        ORDER BY document_chunks.embedding <=> CAST(:query_embedding AS vector)
        LIMIT 10
    """)
    diag_params = {"query_embedding": str(query_embedding)}
    if document_ids:
        diag_params["document_ids"] = document_ids
    if user_id is not None:
        diag_params["user_id"] = user_id
    diag_rows = db.execute(sql_no_threshold, diag_params).mappings().all()
    print(f"[DIAG:retrieval] Raw distances (no threshold, {len(diag_rows)} rows):")
    for r in diag_rows:
        print(f"[DIAG:retrieval]   doc={r['document_id']}  chunk={r['chunk_index']}  dist={r['distance']:.4f}  passes_threshold={r['distance'] <= distance_threshold}")

    # ---------------------------------------------------------
    # PASS 1 — With threshold (unchanged existing behavior)
    # ---------------------------------------------------------

    sql_with_threshold = text(f"""
        SELECT
            document_chunks.id,
            document_chunks.document_id,
            documents.title AS document_title,
            documents.filename AS document_filename,
            document_chunks.chunk_index,
            document_chunks.content,
            document_chunks.embedding <=> CAST(:query_embedding AS vector) AS distance
        FROM document_chunks
        JOIN documents
            ON documents.id = document_chunks.document_id
        WHERE document_chunks.embedding IS NOT NULL
          AND document_chunks.embedding <=> CAST(:query_embedding AS vector) <= :distance_threshold
          {document_filter}
        ORDER BY document_chunks.embedding <=> CAST(:query_embedding AS vector)
        LIMIT :limit
    """)

    params_pass1 = {**base_params, "distance_threshold": distance_threshold}
    rows = db.execute(sql_with_threshold, params_pass1).mappings().all()

    print(f"[DIAG:retrieval] Pass-1 (with threshold={distance_threshold}) → {len(rows)} rows")

    if rows:
        return rows

    # ---------------------------------------------------------
    # PASS 2 — Scoped top-K fallback (no threshold)
    #
    # Only activates when:
    #   - document_ids was provided (investigation-scoped mode)
    #   - Pass 1 returned zero results
    #
    # The document_ids filter is PRESERVED — no global fallback.
    # This handles broad meta-questions such as:
    #   "What is different between the first and second documents?"
    # where the query embedding is semantically distant from all
    # chunk embeddings but the user still needs evidence.
    # ---------------------------------------------------------

    if document_ids is not None:
        print(f"[DIAG:retrieval] Pass-1 returned 0 rows for scoped query → running Pass-2 (top-K, no threshold, SAME document_ids)")

        sql_topk = text(f"""
            SELECT
                document_chunks.id,
                document_chunks.document_id,
                documents.title AS document_title,
                documents.filename AS document_filename,
                document_chunks.chunk_index,
                document_chunks.content,
                document_chunks.embedding <=> CAST(:query_embedding AS vector) AS distance
            FROM document_chunks
            JOIN documents
                ON documents.id = document_chunks.document_id
            WHERE document_chunks.embedding IS NOT NULL
              {document_filter}
            ORDER BY document_chunks.embedding <=> CAST(:query_embedding AS vector)
            LIMIT :limit
        """)

        rows = db.execute(sql_topk, base_params).mappings().all()

        print(f"[DIAG:retrieval] Pass-2 (no threshold, scoped) → {len(rows)} rows")
        for r in rows:
            print(f"[DIAG:retrieval]   doc={r['document_id']}  chunk={r['chunk_index']}  dist={r['distance']:.4f}")

        return rows

    # ---------------------------------------------------------
    # Global RAG with threshold: 0 results → return empty.
    # Do NOT fall back to global library from scoped mode.
    # ---------------------------------------------------------

    print(f"[DIAG:retrieval] Pass-1 returned 0 rows (global RAG) → returning []")
    return rows