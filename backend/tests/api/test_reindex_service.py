"""
Tests for document-scoped transactional reindex operation in reindex_service.py.
Verifies dry-run mode, successful replacement, rollback on failure,
duplicate prevention, and preservation of unrelated documents.
"""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services.reindex_service import (
    ReindexValidationError,
    execute_document_reindex,
    inspect_document_for_reindex,
)


@pytest.fixture
def db():
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture
def test_user(db: Session):
    user = User(
        email=f"reindex_test_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hash",
        role="admin",
        is_active=True,
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def sample_stale_document(db: Session, test_user: User) -> Document:
    """Creates a test document with intentionally stale, mid-word cut chunks."""
    extracted_text = (
        ("SECTION 1. OVERVIEW\n"
         "This specification establishes enterprise operational security safeguards across all services. "
         "All employees and contractors must strictly adhere to governance guidelines.\n\n") * 3
        + ("SECTION 2. ROLES & RESPONSIBILITIES\n"
           "Chief Privacy Officer: Oversees data privacy compliance and breach notification workflows. "
           "Data Stewards: Ensure accuracy and appropriate retention of records.\n\n") * 3
        + ("SECTION 3. CONTINUOUS SCANNING\n"
           "Continuous automated posture scanning must be integrated for all Tier-1 connections. "
           "Weekly posture reports must be archived.\n\n") * 3
        + ("SECTION 4. USER OBLIGATIONS\n"
           "Employees & Contractors: Obligated to adhere to credential hygiene, immediate reporting requirements, and usage guidelines. "
           "Administrative access requires MFA across all production accounts.\n\n") * 3
    )

    doc = Document(
        title="Sample Stale Policy",
        filename="stale_policy.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
        extracted_text=extracted_text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Insert simulated stale chunks (with broken beginnings)
    c0 = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="SECTION 1. OVERVIEW\nThis specification establishes enterprise operational security safeguards.",
    )
    c1 = DocumentChunk(
        document_id=doc.id,
        chunk_index=1,
        content="ta privacy compliance and breach notification workflows. Data Stewards: Ensure accuracy.",
    )
    c2 = DocumentChunk(
        document_id=doc.id,
        chunk_index=2,
        content="ted posture scanning must be integrated for all Tier-1 connections. Weekly reports.",
    )
    db.add_all([c0, c1, c2])
    db.commit()

    return doc


@pytest.fixture
def unrelated_document(db: Session, test_user: User) -> Document:
    """Creates an unrelated document whose chunks must remain untouched."""
    doc = Document(
        title="Unrelated Document",
        filename="unrelated.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
        extracted_text="Unrelated document content that must not be changed.",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    c0 = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        content="Unrelated document chunk content.",
        embedding=[0.1] * 384,
    )
    db.add(c0)
    db.commit()

    return doc


def test_reindex_inspection_and_dry_run_does_not_mutate_db(
    db: Session,
    sample_stale_document: Document,
    unrelated_document: Document,
):
    """
    Verifies that dry-run mode accurately identifies stale chunks and returns a plan
    without modifying, deleting, or adding any database rows.
    """
    initial_chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == sample_stale_document.id)
        .all()
    )
    initial_unrelated_chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == unrelated_document.id)
        .all()
    )

    plan = execute_document_reindex(
        db=db,
        document_id=sample_stale_document.id,
        dry_run=True,
    )

    assert plan["mode"] == "DRY_RUN"
    assert plan["document_id"] == sample_stale_document.id
    assert plan["existing_chunk_count"] == 3
    assert plan["proposed_chunk_count"] >= 3
    assert plan["stale_chunks_detected"] >= 2
    assert plan["status"] == "READY_FOR_EXECUTION"

    # Confirm database was not mutated
    current_chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == sample_stale_document.id)
        .all()
    )
    assert len(current_chunks) == len(initial_chunks)
    assert [c.id for c in current_chunks] == [c.id for c in initial_chunks]

    current_unrelated = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == unrelated_document.id)
        .all()
    )
    assert len(current_unrelated) == len(initial_unrelated_chunks)


def test_reindex_successful_transactional_replacement(
    db: Session,
    sample_stale_document: Document,
    unrelated_document: Document,
):
    """
    Verifies successful execution of document-scoped reindex:
    1. Pre-change backup JSON is created.
    2. Stale chunks are transactionally replaced with boundary-aware chunks.
    3. New chunks have valid, non-null 384-dimensional embeddings.
    4. Document ID and extracted_text are preserved.
    5. Unrelated document chunks are completely unaffected.
    """
    with tempfile.TemporaryDirectory() as temp_backup_dir:
        result = execute_document_reindex(
            db=db,
            document_id=sample_stale_document.id,
            dry_run=False,
            backup_dir=temp_backup_dir,
        )

        assert result["mode"] == "EXECUTE"
        assert result["status"] == "COMPLETED"
        assert result["deleted_chunks"] == 3
        assert result["inserted_chunks"] >= 3

        # Verify backup file was created and contains the old 3 chunks
        backup_file = Path(result["backup_file"])
        assert backup_file.exists()
        import json
        with open(backup_file, "r") as f:
            backup_json = json.load(f)
        assert backup_json["document_id"] == sample_stale_document.id
        assert backup_json["total_chunks"] == 3

        # Verify new chunks in database
        new_chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == sample_stale_document.id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
        assert len(new_chunks) == result["inserted_chunks"]

        # Verify no mid-word prefix truncation remains
        for c in new_chunks:
            first_token = c.content.strip().split()[0]
            assert first_token not in ["ta", "ted", "o", "ignated", "idence"]
            assert c.embedding is not None
            assert len(c.embedding) == 384

        # Verify sequential chunk_index without duplicates
        indices = [c.chunk_index for c in new_chunks]
        assert indices == list(range(len(new_chunks)))

        # Verify unrelated document chunks are unchanged
        unrelated_chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == unrelated_document.id)
            .all()
        )
        assert len(unrelated_chunks) == 1
        assert unrelated_chunks[0].content == "Unrelated document chunk content."


def test_reindex_rollback_on_failure_preserves_original_chunks(
    db: Session,
    sample_stale_document: Document,
):
    """
    Verifies that if embedding generation or validation fails mid-transaction:
    1. The transaction rolls back cleanly.
    2. Original chunks remain intact and identical to their pre-operation state.
    """
    original_chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == sample_stale_document.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    original_ids = [c.id for c in original_chunks]
    original_contents = [c.content for c in original_chunks]

    with tempfile.TemporaryDirectory() as temp_backup_dir:
        # Simulate embedding failure halfway through
        with patch("app.services.reindex_service.generate_embedding", side_effect=RuntimeError("Simulated embedding service outage")):
            with pytest.raises(RuntimeError, match="Simulated embedding service outage"):
                execute_document_reindex(
                    db=db,
                    document_id=sample_stale_document.id,
                    dry_run=False,
                    backup_dir=temp_backup_dir,
                )

    # Verify rollback preserved the exact original chunks
    post_chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == sample_stale_document.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    assert len(post_chunks) == len(original_chunks)
    assert [c.id for c in post_chunks] == original_ids
    assert [c.content for c in post_chunks] == original_contents


def test_reindex_aborts_on_hash_or_filename_mismatch(db: Session, test_user: User):
    """
    Verifies that if a target document ID does not match the expected filename or file hash,
    the operation aborts immediately before modifying anything.
    """
    # Create document with whitelisted ID 39 but mismatched hash
    mismatched_doc = Document(
        id=39,
        title="Tampered Doc",
        filename="STD-PRV-02_Data_Protection_Privacy_Standard.pdf",
        file_hash="tampered_hash_value_12345",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
        extracted_text="Tampered text",
    )
    db.merge(mismatched_doc)
    db.commit()

    with pytest.raises(ReindexValidationError, match="Document hash mismatch"):
        execute_document_reindex(
            db=db,
            document_id=39,
            dry_run=False,
        )


def test_backup_restore_recovers_original_chunks_and_embeddings(
    db: Session,
    sample_stale_document: Document,
):
    """
    Verifies that the JSON backup created before reindexing can fully restore
    the original PostgreSQL chunk records, including IDs, indices, content,
    and 384-dimensional embedding vectors.
    """
    from app.services.reindex_service import restore_document_chunks_from_backup

    original_chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == sample_stale_document.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    original_data = [
        {
            "id": c.id,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "embedding": list(c.embedding) if c.embedding is not None else None,
        }
        for c in original_chunks
    ]

    with tempfile.TemporaryDirectory() as temp_backup_dir:
        # Step 1: Reindex (which creates a backup and replaces the chunks)
        reindex_res = execute_document_reindex(
            db=db,
            document_id=sample_stale_document.id,
            dry_run=False,
            backup_dir=temp_backup_dir,
        )
        backup_file = Path(reindex_res["backup_file"])
        assert backup_file.exists()

        # Confirm chunks changed
        reindexed_chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == sample_stale_document.id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
        assert len(reindexed_chunks) >= len(original_chunks)

        # Step 2: Restore from the verified backup
        restore_res = restore_document_chunks_from_backup(db=db, backup_path=backup_file)
        assert restore_res["status"] == "RESTORED"
        assert restore_res["restored_chunks"] == len(original_chunks)

        # Step 3: Verify restored chunks match the original exactly
        restored_chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == sample_stale_document.id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
        assert len(restored_chunks) == len(original_chunks)
        for rc, orig in zip(restored_chunks, original_data):
            assert rc.id == orig["id"]
            assert rc.chunk_index == orig["chunk_index"]
            assert rc.content == orig["content"]
            assert rc.embedding == orig["embedding"]


def test_proposed_replacement_chunks_derived_from_original_extracted_text():
    """
    Verifies text integrity:
    Ensures every proposed replacement chunk is a literal contiguous substring
    of the original extracted_text, preserving complete words and text flow.
    """
    from app.services.text_chunker import chunk_text

    sample_extracted_text = (
        "SECTION 1. OVERVIEW\n"
        "This specification establishes enterprise operational security safeguards across all services.\n\n"
        "SECTION 2. ROLES & RESPONSIBILITIES\n"
        "Chief Privacy Officer: Oversees data privacy compliance and breach notification workflows.\n"
        "Data Stewards: Ensure accuracy and appropriate retention of records.\n\n"
        "SECTION 3. CONTINUOUS SCANNING\n"
        "Continuous automated posture scanning must be integrated for all Tier-1 connections.\n"
        "Weekly posture reports must be archived.\n\n"
        "SECTION 4. USER OBLIGATIONS\n"
        "Employees & Contractors: Obligated to adhere to credential hygiene, immediate reporting requirements, and usage guidelines.\n"
        "Administrative access requires MFA across all production accounts.\n"
    )

    chunks = chunk_text(sample_extracted_text, chunk_size=180, overlap=50)
    assert len(chunks) >= 3

    for i, c in enumerate(chunks):
        # Every chunk must be a literal substring of the source text
        assert c in sample_extracted_text, f"Chunk {i} is not a verbatim substring of source text!"
        # Every chunk must start and end on whole words
        first_token = c.strip().split()[0]
        last_token = c.strip().split()[-1]
        assert len(first_token) > 1 or first_token.upper() in ["A", "I"]
        assert len(last_token) > 1 or last_token in [".", ":"]


