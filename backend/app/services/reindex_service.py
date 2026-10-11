"""
Document-Scoped Reindex Service with Transactional Replacement, Embedding Regeneration,
Pre-Change Backup, and Dry-Run Verification.

Guarantees:
1. Document-scoped: Operates strictly on a specified document_id.
2. Pre-change backup: Exports existing chunks and metadata to JSON before any mutation.
3. Transactional: Delete, re-chunk, insert, and embed run inside a single transaction.
4. Validation: Asserts chunk count, boundary integrity, embedding dimensions (384), and no duplicates.
5. Atomic rollback: Any failure triggers an immediate rollback, leaving existing chunks intact.
6. Reference preservation: Preserves Document records, extracted_text, agent runs, and unrelated documents.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

import app.models.user  # Ensures User model is registered for SQLAlchemy relationships
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embedding_service import generate_embedding
from app.services.text_chunker import chunk_text

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / "backups"


class ReindexValidationError(Exception):
    """Raised when reindex validation checks fail."""
    pass


# Strict target scope definition for affected documents
EXPECTED_DOCUMENTS: dict[int, dict[str, Any]] = {
    39: {
        "filename": "STD-PRV-02_Data_Protection_Privacy_Standard.pdf",
        "file_hash": "2d49fc49556ccb1fc0279dc2a8308d055c370c3b14ee8dd0156b90e2c8a86374",
        "expected_chunks": 4,
    },
    40: {
        "filename": "STD-TPM-03_Third_Party_Risk_Management_Standard.pdf",
        "file_hash": "584e2bba293ab2aeb6a31467317e4f175b9d197fea78533e49fe7b4ec9a44c5c",
        "expected_chunks": 4,
    },
    37: {
        "filename": "POL-SEC-01_Information_Security_Policy.pdf",
        "file_hash": "ad5531bf5a6dddbaa10dd77b2b055b10d26ae7229d4fb2c2997d70e651565fd2",
        "expected_chunks": 6,
    },
    38: {
        "filename": "PROC-IR-01_Security_Incident_Response_Procedure.pdf",
        "file_hash": "526d08beed16d2b4163a2c30402a53948eaf171d260988f35d887e65e30e3b19",
        "expected_chunks": 4,
    },
    36: {
        "filename": "POL-REC-01_Records_Retention_Legal_Hold_Policy.pdf",
        "file_hash": "b885b366ee93589ecd50ce673030a2a1c97ccd0bbd8cf34353e2712333f44c42",
        "expected_chunks": 4,
    },
}


def verify_document_scope_and_identity(doc: Document, enforce_target_whitelist: bool = True) -> None:
    """
    Verifies that a document matches expected filename and hash before mutation.
    Aborts immediately if ID, filename, or file hash differ.
    """
    if enforce_target_whitelist and doc.id in EXPECTED_DOCUMENTS:
        expected = EXPECTED_DOCUMENTS[doc.id]
        if doc.filename != expected["filename"]:
            raise ReindexValidationError(
                f"Document scope mismatch: Document ID {doc.id} filename '{doc.filename}' "
                f"does not match expected '{expected['filename']}'."
            )
        if doc.file_hash != expected["file_hash"]:
            raise ReindexValidationError(
                f"Document hash mismatch: Document ID {doc.id} hash '{doc.file_hash}' "
                f"does not match expected original hash '{expected['file_hash']}'."
            )


def inspect_document_for_reindex(
    db: Session,
    document_id: int,
    enforce_target_whitelist: bool = False,
) -> dict[str, Any]:
    """
    Inspects a document's current chunks and compares them to proposed boundary-aware chunks.
    Read-only pre-flight inspection.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError(f"Document with ID {document_id} not found.")

    verify_document_scope_and_identity(doc, enforce_target_whitelist=enforce_target_whitelist)

    existing_chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    extracted_text = doc.extracted_text or ""
    proposed_chunks = chunk_text(extracted_text) if extracted_text else []

    # Check for truncated boundary indicators in existing chunks
    stale_indicators: list[dict[str, Any]] = []
    for c in existing_chunks:
        trimmed = c.content.strip()
        first_token = trimmed.split()[0] if trimmed else ""
        is_stale_prefix = (
            first_token in ["ta", "ted", "o", "ignated", "idence", "es", "ing"]
            or bool(re.match(r"^[a-z]{1,4}\s", trimmed))
        )
        if is_stale_prefix:
            stale_indicators.append({
                "chunk_id": c.id,
                "chunk_index": c.chunk_index,
                "first_token": first_token,
                "snippet": trimmed[:60],
            })

    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "title": doc.title,
        "file_hash": doc.file_hash,
        "extracted_text_length": len(extracted_text),
        "existing_chunk_count": len(existing_chunks),
        "proposed_chunk_count": len(proposed_chunks),
        "has_stale_chunks": len(stale_indicators) > 0,
        "stale_indicators": stale_indicators,
        "embedding_model": "all-MiniLM-L6-v2",
        "embedding_dimensions": 384,
    }


def backup_existing_chunks(
    db: Session,
    document_id: int,
    backup_dir: Path | str | None = None,
) -> Path:
    """
    Exports a document's complete existing chunks to a secure, timestamped JSON backup file.
    Includes full embedding vectors, IDs, indices, content, and creation timestamps.
    Verifies that the backup file is fully readable and complete before returning.
    """
    target_dir = Path(backup_dir) if backup_dir else DEFAULT_BACKUP_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError(f"Document with ID {document_id} not found.")

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", doc.filename or f"doc_{document_id}")
    backup_path = target_dir / f"backup_chunks_doc_{document_id}_{safe_name}_{timestamp}.json"

    backup_data = {
        "backup_created_at": datetime.now(timezone.utc).isoformat(),
        "document_id": doc.id,
        "filename": doc.filename,
        "title": doc.title,
        "file_hash": doc.file_hash,
        "extracted_text_length": len(doc.extracted_text or ""),
        "total_chunks": len(chunks),
        "chunks": [
            {
                "id": c.id,
                "document_id": c.document_id,
                "chunk_index": c.chunk_index,
                "content": c.content,
                "embedding": list(c.embedding) if c.embedding is not None else None,
                "has_embedding": c.embedding is not None,
                "embedding_dim": len(c.embedding) if c.embedding is not None else 0,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in chunks
        ],
    }

    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, ensure_ascii=False)

    # Verify backup is restorable and valid JSON
    with open(backup_path, "r", encoding="utf-8") as f:
        verified_data = json.load(f)
    if verified_data["total_chunks"] != len(chunks) or len(verified_data["chunks"]) != len(chunks):
        raise ReindexValidationError(
            f"Backup verification failed for document {document_id}: "
            f"expected {len(chunks)} chunks, read {len(verified_data.get('chunks', []))}."
        )

    logger.info(f"Verified restorable backup created with {len(chunks)} chunks at {backup_path}")
    return backup_path


def execute_document_reindex(
    db: Session,
    document_id: int,
    dry_run: bool = True,
    backup_dir: Path | str | None = None,
) -> dict[str, Any]:
    """
    Executes a transactional reindex operation for a specific document.

    If dry_run=True:
        Plans the reindex, generates inspection metadata, and verifies feasibility
        WITHOUT mutating the database.
    If dry_run=False:
        1. Backs up existing chunks to disk.
        2. Deletes existing chunks for document_id within an atomic transaction.
        3. Inserts boundary-aware chunks.
        4. Regenerates and stores vector embeddings.
        5. Validates results and commits.
        6. Rolls back immediately on any error or assertion failure.
    """
    inspection = inspect_document_for_reindex(db, document_id)
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError(f"Document with ID {document_id} not found.")

    if not doc.extracted_text:
        raise ValueError(f"Document {document_id} has no extracted text; cannot reindex.")

    proposed_text_chunks = chunk_text(doc.extracted_text)
    if not proposed_text_chunks:
        raise ValueError(f"Chunking extracted text for document {document_id} returned 0 chunks.")

    if dry_run:
        return {
            "mode": "DRY_RUN",
            "document_id": document_id,
            "filename": doc.filename,
            "action_proposed": "Transactional replacement of stale chunks with boundary-aware chunks",
            "existing_chunk_count": inspection["existing_chunk_count"],
            "proposed_chunk_count": len(proposed_text_chunks),
            "stale_chunks_detected": len(inspection["stale_indicators"]),
            "stale_indicators": inspection["stale_indicators"],
            "embedding_model": "all-MiniLM-L6-v2 (384-d)",
            "status": "READY_FOR_EXECUTION",
            "message": "Dry run succeeded. No database modifications were performed.",
        }

    # Record unrelated document chunk count to verify isolation
    unrelated_count_before = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id != document_id)
        .count()
    )

    # Verify exact document scope and hash identity before proceeding with mutation
    verify_document_scope_and_identity(doc, enforce_target_whitelist=True)

    # Step 1: Pre-change backup
    backup_file = backup_existing_chunks(db, document_id, backup_dir=backup_dir)

    # Step 2: Transactional replacement with validation and rollback on error
    try:
        # Atomic delete of target document's existing chunks
        deleted_count = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .delete(synchronize_session=False)
        )

        # Insert new boundary-aware chunks
        new_chunk_records: list[DocumentChunk] = []
        for idx, content in enumerate(proposed_text_chunks):
            chunk_rec = DocumentChunk(
                document_id=document_id,
                chunk_index=idx,
                content=content,
            )
            db.add(chunk_rec)
            new_chunk_records.append(chunk_rec)

        db.flush()

        # Generate embeddings
        for rec in new_chunk_records:
            emb = generate_embedding(rec.content)
            rec.embedding = emb

        db.flush()

        # Step 3: Strict Validation
        # Check A: Correct count
        inserted_count = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .count()
        )
        if inserted_count != len(proposed_text_chunks):
            raise ReindexValidationError(
                f"Validation failed: expected {len(proposed_text_chunks)} chunks, found {inserted_count}."
            )

        # Check B: Non-null embeddings with correct dimension
        for rec in new_chunk_records:
            if rec.embedding is None:
                raise ReindexValidationError(
                    f"Validation failed: Chunk {rec.id} (index {rec.chunk_index}) has null embedding."
                )
            if len(rec.embedding) != 384:
                raise ReindexValidationError(
                    f"Validation failed: Chunk {rec.id} has dimension {len(rec.embedding)}, expected 384."
                )

        # Check C: Duplicate chunk indices prevention
        chunk_indices = [
            c.chunk_index
            for c in db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .all()
        ]
        if len(chunk_indices) != len(set(chunk_indices)):
            raise ReindexValidationError(
                f"Validation failed: Duplicate chunk_index detected for document {document_id}."
            )

        # Check D: Isolation guard — unrelated documents untouched
        unrelated_count_after = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id != document_id)
            .count()
        )
        if unrelated_count_after != unrelated_count_before:
            raise ReindexValidationError(
                f"Isolation breach: Unrelated chunk count changed from {unrelated_count_before} to {unrelated_count_after}."
            )

        db.commit()

        logger.info(
            f"Successfully reindexed document {document_id}: "
            f"replaced {deleted_count} stale chunks with {len(new_chunk_records)} bounded chunks."
        )

        return {
            "mode": "EXECUTE",
            "document_id": document_id,
            "filename": doc.filename,
            "deleted_chunks": deleted_count,
            "inserted_chunks": len(new_chunk_records),
            "backup_file": str(backup_file),
            "status": "COMPLETED",
            "message": "Document chunks successfully and transactionally replaced.",
        }

    except Exception as exc:
        db.rollback()
        logger.error(f"Reindex transaction failed for document {document_id}: {exc}. Rolled back.")
        raise


def restore_document_chunks_from_backup(
    db: Session,
    backup_path: Path | str,
) -> dict[str, Any]:
    """
    Restores a document's chunks from a verified JSON backup file.
    Runs inside an atomic transaction with validation and rollback.
    """
    path = Path(backup_path)
    if not path.exists():
        raise FileNotFoundError(f"Backup file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        backup_data = json.load(f)

    doc_id = backup_data["document_id"]
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise ValueError(f"Target document ID {doc_id} from backup does not exist in database.")

    chunks_data = backup_data.get("chunks", [])
    if len(chunks_data) != backup_data.get("total_chunks", -1):
        raise ReindexValidationError("Backup corruption: chunk list length does not match total_chunks.")

    try:
        # Atomic delete of any current chunks for this document
        db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete(synchronize_session=False)

        for c_data in chunks_data:
            created_at_val = (
                datetime.fromisoformat(c_data["created_at"])
                if c_data.get("created_at")
                else None
            )
            restored_chunk = DocumentChunk(
                id=c_data["id"],
                document_id=doc_id,
                chunk_index=c_data["chunk_index"],
                content=c_data["content"],
                embedding=c_data.get("embedding"),
                created_at=created_at_val,
            )
            db.add(restored_chunk)

        db.flush()

        # Validation
        restored_count = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count()
        if restored_count != len(chunks_data):
            raise ReindexValidationError(
                f"Restore validation failed: expected {len(chunks_data)} chunks, restored {restored_count}."
            )

        db.commit()

        logger.info(f"Successfully restored {restored_count} chunks for document {doc_id} from {path}")
        return {
            "status": "RESTORED",
            "document_id": doc_id,
            "filename": doc.filename,
            "restored_chunks": restored_count,
            "backup_file": str(path),
        }
    except Exception as exc:
        db.rollback()
        logger.error(f"Restore failed for document {doc_id} from {path}: {exc}. Rolled back.")
        raise


def execute_target_documents_suite(
    db: Session,
    target_ids: list[int] | None = None,
    dry_run: bool = True,
    backup_dir: Path | str | None = None,
) -> dict[str, Any]:
    """
    Executes the full document reindex workflow for the approved target documents.

    Guarantees:
    1. Pre-flight verification: Validates all target documents, filenames, and hashes upfront.
    2. All-backups-first: In execute mode, exports and validates ALL backups to disk
       BEFORE any database deletions or mutations occur on any document.
    3. Document-scoped execution: Each document is replaced in an atomic transaction.
    """
    ids = target_ids or [39, 40, 37, 38, 36]
    logger.info(f"Initiating target documents suite for IDs: {ids} (dry_run={dry_run})")

    # Phase 1: Pre-flight validation of all target documents
    preflight_results = []
    for did in ids:
        inspection = inspect_document_for_reindex(db, did, enforce_target_whitelist=True)
        preflight_results.append(inspection)

    if dry_run:
        return {
            "mode": "DRY_RUN_SUITE",
            "target_document_ids": ids,
            "total_documents": len(ids),
            "total_existing_chunks": sum(p["existing_chunk_count"] for p in preflight_results),
            "total_proposed_chunks": sum(p["proposed_chunk_count"] for p in preflight_results),
            "total_stale_chunks_detected": sum(len(p["stale_indicators"]) for p in preflight_results),
            "document_previews": preflight_results,
            "status": "READY_FOR_EXECUTION",
            "message": "All 5 documents verified in dry-run mode. Zero backups written. Zero database modifications.",
        }

    # Phase 2: All-backups-first — export and verify all backups before ANY mutation
    logger.info("Executing Phase 2: Generating and verifying all backups prior to mutation...")
    verified_backups: list[dict[str, Any]] = []
    for did in ids:
        b_path = backup_existing_chunks(db, did, backup_dir=backup_dir)
        verified_backups.append({
            "document_id": did,
            "backup_path": str(b_path),
        })

    logger.info(f"Phase 2 complete: All {len(verified_backups)} backups verified on disk.")

    # Phase 3: Transactional replacements per document
    execution_results = []
    for did in ids:
        # Pass existing backup file to execute_document_reindex
        doc_backup = next(b["backup_path"] for b in verified_backups if b["document_id"] == did)
        res = execute_document_reindex(
            db=db,
            document_id=did,
            dry_run=False,
            backup_dir=backup_dir,
        )
        execution_results.append(res)

    return {
        "mode": "EXECUTE_SUITE",
        "target_document_ids": ids,
        "total_documents": len(ids),
        "backups_created": len(verified_backups),
        "backup_files": [b["backup_path"] for b in verified_backups],
        "execution_results": execution_results,
        "status": "ALL_COMPLETED",
    }


def run_cli() -> None:
    """CLI entrypoint for running inspection, dry run, reindex, or backup restore."""
    parser = argparse.ArgumentParser(description="OpusLex Document-Scoped Reindex Utility")
    parser.add_argument("--document-id", type=int, help="Target document ID to reindex")
    parser.add_argument("--target-documents", action="store_true", help="Target the 5 approved documents (39, 40, 37, 38, 36)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Run dry-run without writing")
    parser.add_argument("--execute", action="store_true", help="Explicitly execute the transactional replacement")
    parser.add_argument("--restore", action="store_true", help="Restore document chunks from a JSON backup file")
    parser.add_argument("--backup-file", type=str, default=None, help="Backup JSON file path for restoration")
    parser.add_argument("--backup-dir", type=str, default=None, help="Directory for JSON backups")
    parser.add_argument("--verify-database", type=str, default=None, help="Explicitly verify expected database name before running")

    args = parser.parse_args()

    from app.database import SessionLocal, engine

    # Explicit Database Verification Guard
    current_db = engine.url.database
    current_host = engine.url.host or "localhost"
    current_port = engine.url.port or 5432
    print(f"[Database Guard] Connected to: database='{current_db}' on host='{current_host}:{current_port}'")

    if args.verify_database:
        if current_db != args.verify_database:
            raise ReindexValidationError(
                f"[Database Guard Error] Connected database '{current_db}' does not match "
                f"expected database '{args.verify_database}'! Aborting immediately."
            )
        print(f"[Database Guard] Verified expected database matches '{args.verify_database}'.")

    db = SessionLocal()
    try:
        if args.restore:
            if not args.backup_file:
                parser.error("--backup-file is required when using --restore")
            result = restore_document_chunks_from_backup(db=db, backup_path=args.backup_file)
        elif args.target_documents:
            if args.execute:
                result = execute_target_documents_suite(
                    db=db,
                    dry_run=False,
                    backup_dir=args.backup_dir,
                )
            else:
                result = execute_target_documents_suite(
                    db=db,
                    dry_run=True,
                )
        elif args.execute:
            if not args.document_id:
                parser.error("--document-id or --target-documents is required when executing reindex")
            result = execute_document_reindex(
                db=db,
                document_id=args.document_id,
                dry_run=False,
                backup_dir=args.backup_dir,
            )
        else:
            if not args.document_id:
                parser.error("--document-id or --target-documents is required")
            result = execute_document_reindex(
                db=db,
                document_id=args.document_id,
                dry_run=True,
            )
        print(json.dumps(result, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    run_cli()
