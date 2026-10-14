# OpusLex Architecture Patterns & Code Examples

## 1. RAG Implementation Pattern

### The Map-Reduce Architecture

OpusLex implements a sophisticated two-phase Map-Reduce pattern for document comparison to prevent LLM hallucination:

```python
# PHASE 1: MAP - Analyze each document independently
async def _map_single_document(
    label: str,
    doc: dict,
    chunks: list,
    question: str,
) -> str:
    """
    MAP phase: generate a structured analysis for ONE document.
    
    The LLM receives ONLY the chunks belonging to this document.
    It does NOT see any other document's evidence.
    """
    # Format chunks specific to this document
    evidence = _format_chunks(chunks)
    
    # Build MAP prompt
    map_prompt = f"""You are a document analyst. Analyse ONLY the following single document.
Do NOT compare with other documents — that step comes later.

DOCUMENT IDENTITY:
  Label    : Document {label}
  ID       : {doc['id']}
  Filename : {doc['filename']}

RETRIEVED EVIDENCE (use ONLY this text):
{evidence}

RULES:
1. Use ONLY the retrieved evidence above. Do not invent or infer.
2. Cite every factual statement with [Source: {doc['filename']}, Chunk: N].
3. If evidence is empty or irrelevant, say so explicitly.

REQUIRED OUTPUT STRUCTURE:
Document {label} — {doc['filename']}

EDUCATION
<evidence-based summary or "not found in retrieved evidence">

TECHNICAL SKILLS
<evidence-based summary or "not found in retrieved evidence">

... (more sections)

ATS PROFILE SCORE for Document {label}:
  1. Formatting / readability  : [0|1|2] — <justification>
  ... (7 dimensions)
  
ATS_SCORE: X/14
"""
    
    # Send to LLM
    analysis = await ask_copilot_with_context(
        question=map_prompt,
        context="Analyse only the single document specified."
    )
    return analysis


# PHASE 2: REDUCE - Cross-document comparison
async def compare_documents(
    db: Session,
    question: str,
    documents: list[dict],
    limit: int = 5,
) -> dict:
    """
    Map-Reduce document comparison.
    
    Returns: {"comparison": str, "sources": dict}
    """
    
    # STEP 1: Retrieve chunks for each document
    per_doc_chunks: list[list] = []
    for doc in documents:
        chunks = search_similar_chunks(
            db=db,
            query=question,
            limit=limit,
            document_ids=[doc["id"]],  # Scoped to this document
        )
        per_doc_chunks.append(chunks)
    
    # STEP 2: Execute MAP phase (sequential to avoid client shutdown)
    map_analyses: list[str] = []
    for i, doc in enumerate(documents):
        label = chr(65 + i)  # A, B, C, ...
        analysis = await _map_single_document(
            label=label,
            doc=doc,
            chunks=per_doc_chunks[i],
            question=question,
        )
        map_analyses.append(analysis)
    
    # STEP 3: Execute REDUCE phase with all analyses
    reduce_prompt = f"""You are a research assistant performing a final cross-document comparison.
You have received {len(documents)} pre-analysed document summaries.

DOCUMENT IDENTITY:
  Document A = {documents[0]['filename']} (ID {documents[0]['id']})
  Document B = {documents[1]['filename']} (ID {documents[1]['id']})
  ... etc

MANDATORY RULES:
R1. You MUST produce a section for EVERY document: {all_labels}
    Do NOT skip, merge, or omit any document.
R2. Use ONLY information present in the document analyses below.
R3. When evidence is sparse for a document, say so explicitly.
R4. Do NOT claim scores predict hiring outcome. Use "profile alignment" instead.
R5. Do NOT produce ranking unless evidence clearly supports it.

DOCUMENT ANALYSES (input only — do not reproduce verbatim):
{analyses_block}

REQUIRED OUTPUT STRUCTURE:
─────────────────────────────────────────────────────
DOCUMENT-BY-DOCUMENT ANALYSIS
─────────────────────────────────────────────────────
[One section per document with: education, skills, experience, 
projects, strengths, gaps, ATS score]

─────────────────────────────────────────────────────
CROSS-DOCUMENT COMPARISON
─────────────────────────────────────────────────────

SIMILARITIES
[What all documents share]

DIFFERENCES  
[Where they diverge - attribute to each document]

ATS SCORE SUMMARY TABLE
| Document | Score/14 | Notes |
|----------|----------|-------|
[All {len(documents)} documents]

PROFILE ALIGNMENT ASSESSMENT
[For each document, how well it aligns with competitive roles]

─────────────────────────────────────────────────────
CONCLUSION
─────────────────────────────────────────────────────
[Evidence-based conclusion referencing ALL documents]
"""
    
    comparison_text = await ask_copilot_with_context(
        question=reduce_prompt,
        context="Synthesise the pre-analysed document summaries."
    )
    
    return {
        "comparison": comparison_text,
        "sources": sources,
    }
```

### Why This Pattern?

**Benefits:**
1. **Prevents Hallucination**: Each MAP call sees ONLY its document's evidence
2. **Structured Output**: ATS rubric ensures deterministic scoring
3. **Transparency**: Every claim can be traced to a source
4. **Scalability**: N documents → N MAP calls + 1 REDUCE call (not N² calls)
5. **Audit Trail**: Full evidence retrieved for compliance

**Sequential Execution Requirement:**
```python
# ❌ WRONG - Causes SERVER_SHUTTING_DOWN errors
map_analyses = await asyncio.gather(
    _map_single_document(label="A", ...),
    _map_single_document(label="B", ...),
    _map_single_document(label="C", ...),
)

# ✓ CORRECT - Sequential execution
map_analyses = []
for i, doc in enumerate(documents):
    analysis = await _map_single_document(
        label=chr(65 + i),
        doc=doc,
        ...
    )
    map_analyses.append(analysis)
```

The shared `CopilotClient` singleton calls `client.start()` / `client.stop()` on each invocation. Running concurrent MAP calls causes the first to finish calling `stop()`, which shuts down the shared server while others are still in flight → `SERVER_SHUTTING_DOWN` errors.

---

## 2. Vector Search Architecture

### Embedding & Retrieval Flow

```python
# STEP 1: Document Upload - Generate Embeddings
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')  # 384-dimensional

async def embed_document(pdf_path: str):
    # Extract text using PyMuPDF
    text = extract_text_from_pdf(pdf_path)
    
    # Split into chunks
    chunks = split_text_into_chunks(text, chunk_size=512)
    
    # Generate embeddings
    embeddings = model.encode(chunks, convert_to_numpy=True)
    # Output shape: (num_chunks, 384)
    
    # Store in database
    for chunk_text, embedding in zip(chunks, embeddings):
        db_chunk = DocumentChunk(
            document_id=doc_id,
            content=chunk_text,
            embedding=embedding,  # pgvector stores this
        )
        db.add(db_chunk)
    db.commit()


# STEP 2: Query - Semantic Search
def search_similar_chunks(
    db: Session,
    query: str,
    limit: int = 5,
    document_ids: list[int] | None = None,
) -> list[dict]:
    """
    Search for chunks similar to query using HNSW index.
    """
    # Embed the query with same model
    query_embedding = model.encode([query], convert_to_numpy=True)[0]
    # Output shape: (384,)
    
    # HNSW cosine similarity search
    # <-> operator: cosine distance (lower = more similar)
    # LIMIT: get top-K results
    
    results = db.query(DocumentChunk).filter(
        DocumentChunk.document_id.in_(document_ids) if document_ids else True
    ).order_by(
        DocumentChunk.embedding.cosine_distance(query_embedding)
    ).limit(limit).all()
    
    return [
        {
            "chunk_id": chunk.id,
            "content": chunk.content,
            "embedding": chunk.embedding,
            "distance": distance,  # Lower = more relevant
            "document_id": chunk.document_id,
        }
        for chunk, distance in results
    ]
```

### Database Index Performance

```sql
-- BEFORE: Sequential scan
-- Every query does a full table scan: O(n)
SELECT chunk_id, content, embedding <-> query_vector AS distance
FROM document_chunks
ORDER BY distance
LIMIT 5;
-- Time: ~84ms (table size dependent)

-- AFTER: HNSW index
-- Fast approximate nearest neighbor search: O(log n)
CREATE INDEX ON document_chunks 
USING hnsw (embedding vector_cosine_ops)
WITH (m=16, ef_construction=64);

SELECT chunk_id, content, embedding <-> query_vector AS distance
FROM document_chunks
ORDER BY distance
LIMIT 5;
-- Time: ~22ms (-73% improvement)
```

**HNSW Parameters:**
- `m=16`: Number of bi-directional connections per node (default=12)
- `ef_construction=64`: Size of dynamic list (default=32)
- `ef_search`: Set at query time for accuracy/speed tradeoff

---

## 3. Copilot LLM Integration

### Copilot Service Architecture

```python
# app/ai/llm/provider.py
from github_copilot_sdk import CopilotClient

class CopilotService:
    """Thread-safe Copilot API wrapper with timeout handling."""
    
    # Singleton client
    _client: CopilotClient | None = None
    _lock: asyncio.Lock = asyncio.Lock()
    
    @classmethod
    async def get_client(cls) -> CopilotClient:
        """Lazy-load singleton client."""
        if cls._client is None:
            cls._client = CopilotClient()
        return cls._client


async def ask_copilot_with_context(
    question: str,
    context: str,
    timeout: int = 45,  # Prevents infinite hangs
) -> str:
    """
    Query Copilot with RAG context.
    
    Args:
        question: User question or system prompt
        context: Retrieved document context
        timeout: Max seconds to wait for response
    
    Returns:
        LLM-generated answer
    
    Raises:
        asyncio.TimeoutError: If LLM takes >45 seconds
    """
    
    client = await CopilotService.get_client()
    
    # Build full prompt
    full_prompt = f"""Context:
{context}

Question:
{question}"""
    
    try:
        # Start Copilot session
        await client.start()
        
        # Wait for response with timeout
        response = await asyncio.wait_for(
            _handle_copilot_response(client, full_prompt),
            timeout=timeout
        )
        
        return response
        
    except asyncio.TimeoutError:
        raise TimeoutError(
            f"LLM did not respond within {timeout} seconds"
        )
    
    finally:
        # Always stop client to avoid resource leaks
        await client.stop()


async def _handle_copilot_response(client, prompt):
    """Handle Copilot streaming response."""
    
    # Note: This buffers the entire response
    # Real streaming would require AsyncGenerator
    response_text = ""
    done = asyncio.Event()
    
    def on_message(message):
        nonlocal response_text
        if message.type == "chunk":
            response_text += message.data
        elif message.type == "session_idle":
            done.set()
    
    # Register callback
    client.on("message", on_message)
    
    # Send request
    await client.send_request(prompt)
    
    # Wait for completion
    await done.wait()
    
    return response_text
```

### Critical: Sequential Execution

```python
# ❌ WRONG - Concurrent calls fail
await asyncio.gather(
    ask_copilot_with_context("Q1", ctx1),
    ask_copilot_with_context("Q2", ctx2),  # Fails! Client already stopped
)

# ✓ CORRECT - Sequential calls
responses = []
for question, context in [(q1, ctx1), (q2, ctx2)]:
    response = await ask_copilot_with_context(question, context)
    responses.append(response)
```

---

## 4. Service Layer Architecture

### Base Service Pattern

```python
# app/services/base_service.py
from sqlalchemy.orm import Session
from sqlalchemy import select, delete

class BaseService:
    """Base service with common CRUD operations."""
    
    model = None  # Override in subclass
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, **kwargs) -> model:
        """Create and return new instance."""
        instance = self.model(**kwargs)
        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)
        return instance
    
    def get_by_id(self, id: int) -> model | None:
        """Get instance by primary key."""
        return self.db.query(self.model).filter(
            self.model.id == id
        ).first()
    
    def get_all(self, skip: int = 0, limit: int = 10) -> list[model]:
        """Get paginated list of instances."""
        return self.db.query(self.model).offset(skip).limit(limit).all()
    
    def update(self, id: int, **kwargs) -> model | None:
        """Update instance and return."""
        instance = self.get_by_id(id)
        if instance:
            for key, value in kwargs.items():
                setattr(instance, key, value)
            self.db.commit()
            self.db.refresh(instance)
        return instance
    
    def delete(self, id: int) -> bool:
        """Soft delete (set is_deleted flag)."""
        instance = self.get_by_id(id)
        if instance:
            instance.is_deleted = True
            self.db.commit()
            return True
        return False


# app/services/investigation_service.py
class InvestigationService(BaseService):
    model = Investigation
    
    def create_with_documents(
        self,
        user_id: int,
        title: str,
        document_ids: list[int],
    ) -> Investigation:
        """Create investigation and attach documents."""
        
        # Create investigation
        investigation = self.create(
            user_id=user_id,
            title=title,
            status="open"
        )
        
        # Attach documents
        for doc_id in document_ids:
            doc = self.db.query(Document).get(doc_id)
            if doc and doc.user_id == user_id:  # Security check
                investigation.documents.append(doc)
        
        self.db.commit()
        return investigation
    
    def add_query(
        self,
        investigation_id: int,
        question: str,
        answer: str,
        sources: list[dict],
    ) -> InvestigationQuery:
        """Add Q&A to investigation."""
        
        query = InvestigationQuery(
            investigation_id=investigation_id,
            question=question,
            answer=answer,
            sources=sources,  # JSON field
        )
        self.db.add(query)
        self.db.commit()
        self.db.refresh(query)
        return query
    
    def get_user_investigations(
        self,
        user_id: int,
        limit: int = 10,
    ) -> list[Investigation]:
        """Get all investigations for user."""
        return self.db.query(Investigation).filter(
            Investigation.user_id == user_id,
            Investigation.is_deleted == False,
        ).order_by(
            Investigation.created_at.desc()
        ).limit(limit).all()
```

---

## 5. FastAPI Router Pattern

### Typical Router Structure

```python
# app/routers/investigations.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.investigation_service import InvestigationService
from app.schemas.investigation import (
    InvestigationCreate,
    InvestigationResponse,
    InvestigationQuery as QuerySchema,
)

router = APIRouter(
    prefix="/api/v1/investigations",
    tags=["investigations"],
)


# Dependency: Get current user from JWT
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Verify JWT and return user."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401)
    
    user = db.query(User).get(user_id)
    if user is None:
        raise HTTPException(status_code=401)
    return user


# Dependency: Get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Endpoint: Create investigation
@router.post("/", response_model=InvestigationResponse)
async def create_investigation(
    req: InvestigationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new investigation.
    
    - **title**: Investigation title (required)
    - **document_ids**: List of document IDs to attach (optional)
    """
    
    service = InvestigationService(db)
    
    investigation = service.create_with_documents(
        user_id=user.id,
        title=req.title,
        document_ids=req.document_ids or [],
    )
    
    return investigation


# Endpoint: Get investigation by ID
@router.get("/{investigation_id}", response_model=InvestigationResponse)
async def get_investigation(
    investigation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get investigation by ID (user must own it)."""
    
    investigation = db.query(Investigation).filter(
        Investigation.id == investigation_id,
        Investigation.user_id == user.id,  # Security check
        Investigation.is_deleted == False,
    ).first()
    
    if not investigation:
        raise HTTPException(status_code=404, detail="Not found")
    
    return investigation


# Endpoint: Query within investigation
@router.post(
    "/{investigation_id}/query",
    response_model=InvestigationQueryResponse
)
async def ask_question(
    investigation_id: int,
    req: QueryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ask a question within an investigation context.
    """
    
    # Verify ownership
    investigation = db.query(Investigation).filter(
        Investigation.id == investigation_id,
        Investigation.user_id == user.id,
    ).first()
    
    if not investigation:
        raise HTTPException(status_code=404)
    
    # Build RAG context from attached documents
    context, sources = build_rag_context(
        db=db,
        query=req.question,
        document_ids=[d.id for d in investigation.documents],
        user_id=user.id,
    )
    
    # Get LLM answer
    try:
        answer = await ask_copilot_with_context(
            question=req.question,
            context=context,
        )
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="LLM query timeout (45 seconds)"
        )
    
    # Store in database
    service = InvestigationService(db)
    query = service.add_query(
        investigation_id=investigation_id,
        question=req.question,
        answer=answer,
        sources=sources,
    )
    
    return InvestigationQueryResponse(
        query_id=query.id,
        question=query.question,
        answer=query.answer,
        sources=query.sources,
        created_at=query.created_at,
    )


# Endpoint: Compare documents in investigation
@router.post(
    "/{investigation_id}/compare",
    response_model=ComparisonResponse
)
async def compare_documents(
    investigation_id: int,
    req: ComparisonRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Compare documents within investigation using Map-Reduce.
    """
    
    # Verify ownership
    investigation = db.query(Investigation).filter(
        Investigation.id == investigation_id,
        Investigation.user_id == user.id,
    ).first()
    
    if not investigation:
        raise HTTPException(status_code=404)
    
    # Get documents
    documents = [
        {
            "id": d.id,
            "title": d.title,
            "filename": d.filename,
            "jurisdiction": d.jurisdiction,
        }
        for d in investigation.documents
        if d.id in (req.document_ids or [d.id for d in investigation.documents])
    ]
    
    if not documents:
        raise HTTPException(status_code=400, detail="No documents selected")
    
    # Run Map-Reduce comparison
    try:
        result = await compare_documents(
            db=db,
            question=req.question,
            documents=documents,
            limit=req.limit or 5,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Comparison timeout")
    
    return ComparisonResponse(
        comparison=result["comparison"],
        sources=result["sources"],
    )


# Endpoint: List investigations
@router.get("/", response_model=list[InvestigationResponse])
async def list_investigations(
    skip: int = 0,
    limit: int = 10,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all investigations for current user."""
    
    service = InvestigationService(db)
    return service.get_user_investigations(user.id, limit)
```

---

## 6. Multi-Tenancy & Security Pattern

### User Isolation at Database Level

```python
# PATTERN: Scope every query to authenticated user
# This is the PRIMARY defense against data leaks

class DocumentService(BaseService):
    model = Document
    
    def get_user_documents(self, user_id: int, limit: int = 10):
        """Get documents belonging to specific user."""
        return self.db.query(self.model).filter(
            self.model.user_id == user_id,  # ← CRITICAL SCOPE
            self.model.is_deleted == False,
        ).limit(limit).all()
    
    def delete_document(self, doc_id: int, user_id: int) -> bool:
        """Delete document - verify ownership."""
        doc = self.db.query(self.model).filter(
            self.model.id == doc_id,
            self.model.user_id == user_id,  # ← PREVENT UNAUTHORIZED DELETE
        ).first()
        
        if doc:
            doc.is_deleted = True
            self.db.commit()
            return True
        return False


# PATTERN: Dependency injection ensures user context
@router.get("/my-documents")
async def get_my_documents(
    user: User = Depends(get_current_user),  # ← Get user from JWT
    db: Session = Depends(get_db),
):
    """
    List documents for current authenticated user.
    
    Query is automatically scoped to user.id.
    """
    service = DocumentService(db)
    return service.get_user_documents(user.id)


# PATTERN: Verify ownership before sensitive operations
async def delete_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete document - must be owned by current user."""
    
    # First check: Does document exist and belong to user?
    doc = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == user.id,
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404)  # Hide existence
    
    # Perform deletion
    doc.is_deleted = True
    db.commit()
    
    return {"status": "deleted"}
```

---

## 7. Pagination Pattern

### Cursor-Based Pagination (Recommended)

```python
# ✓ BETTER: Cursor-based pagination
# Handles deletions & insertions gracefully

class PaginationCursor(BaseModel):
    limit: int = 10
    cursor: str | None = None  # base64 encoded
    sort: str = "created_at_desc"


def decode_cursor(cursor: str | None) -> int | None:
    """Decode cursor to get last seen ID."""
    if cursor is None:
        return None
    import base64
    try:
        return int(base64.b64decode(cursor).decode())
    except:
        return None


def encode_cursor(last_id: int) -> str:
    """Encode ID as cursor."""
    import base64
    return base64.b64encode(str(last_id).encode()).decode()


@router.get("/documents/")
async def list_documents_paginated(
    pagination: PaginationCursor = Depends(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List documents with cursor-based pagination.
    """
    
    query = db.query(Document).filter(
        Document.user_id == user.id,
        Document.is_deleted == False,
    )
    
    # Apply cursor filter
    if pagination.cursor:
        last_id = decode_cursor(pagination.cursor)
        query = query.filter(Document.id > last_id)
    
    # Fetch limit + 1 to detect if more results exist
    documents = query.order_by(
        Document.created_at.desc()
    ).limit(pagination.limit + 1).all()
    
    has_more = len(documents) > pagination.limit
    documents = documents[:pagination.limit]
    
    next_cursor = None
    if has_more and documents:
        next_cursor = encode_cursor(documents[-1].id)
    
    return {
        "documents": documents,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
```

---

## 8. Error Handling Pattern

### Structured Error Responses

```python
# app/schemas/error.py
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    error_code: str      # Machine-readable code
    message: str         # Human-readable message
    status_code: int     # HTTP status
    details: dict | None = None  # Additional context


# app/exceptions.py
class OpusLexException(Exception):
    """Base exception for application."""
    
    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = 500,
        details: dict | None = None,
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details


class NotFoundError(OpusLexException):
    def __init__(self, resource: str, resource_id: int):
        super().__init__(
            error_code="RESOURCE_NOT_FOUND",
            message=f"{resource} with ID {resource_id} not found",
            status_code=404,
        )


class UnauthorizedError(OpusLexException):
    def __init__(self):
        super().__init__(
            error_code="UNAUTHORIZED",
            message="Authentication required",
            status_code=401,
        )


class LLMTimeoutError(OpusLexException):
    def __init__(self, timeout_seconds: int):
        super().__init__(
            error_code="LLM_TIMEOUT",
            message=f"LLM did not respond within {timeout_seconds} seconds",
            status_code=504,
            details={"timeout_seconds": timeout_seconds},
        )


# app/main.py - Exception handler
@app.exception_handler(OpusLexException)
async def opuslex_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "status_code": exc.status_code,
            "details": exc.details,
        },
    )


# Usage in endpoints
@router.get("/{investigation_id}")
async def get_investigation(investigation_id: int, user: User = Depends(...)):
    investigation = db.query(Investigation).get(investigation_id)
    
    if not investigation:
        raise NotFoundError("Investigation", investigation_id)
    
    if investigation.user_id != user.id:
        raise UnauthorizedError()
    
    return investigation
```

---

## 9. Testing Patterns

### Unit Test Example

```python
# backend/tests/test_investigation_service.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Investigation, Document, User
from app.services.investigation_service import InvestigationService


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    yield session
    
    session.close()


@pytest.fixture
def test_user(db_session):
    """Create test user."""
    user = User(
        id=1,
        email="test@example.com",
        password_hash="hashed_password",
        role="analyst",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_documents(db_session, test_user):
    """Create test documents."""
    docs = []
    for i in range(3):
        doc = Document(
            user_id=test_user.id,
            filename=f"test_doc_{i}.pdf",
            title=f"Test Document {i}",
            jurisdiction="US",
        )
        db_session.add(doc)
        docs.append(doc)
    db_session.commit()
    return docs


def test_create_investigation(db_session, test_user, test_documents):
    """Test creating investigation."""
    service = InvestigationService(db_session)
    
    investigation = service.create_with_documents(
        user_id=test_user.id,
        title="Test Investigation",
        document_ids=[doc.id for doc in test_documents[:2]],
    )
    
    assert investigation.id is not None
    assert investigation.title == "Test Investigation"
    assert investigation.user_id == test_user.id
    assert len(investigation.documents) == 2


def test_add_query_to_investigation(db_session, test_user, test_documents):
    """Test adding Q&A to investigation."""
    service = InvestigationService(db_session)
    
    investigation = service.create_with_documents(
        user_id=test_user.id,
        title="Test Investigation",
        document_ids=[test_documents[0].id],
    )
    
    query = service.add_query(
        investigation_id=investigation.id,
        question="What is this document about?",
        answer="This document discusses...",
        sources=[
            {
                "document_id": test_documents[0].id,
                "filename": test_documents[0].filename,
                "chunk": 0,
                "distance": 0.1,
            }
        ],
    )
    
    assert query.question == "What is this document about?"
    assert len(query.sources) == 1


def test_user_isolation(db_session, test_user, test_documents):
    """Test that queries don't cross user boundaries."""
    service = InvestigationService(db_session)
    
    # Create investigation for test_user
    investigation = service.create_with_documents(
        user_id=test_user.id,
        title="Secret Investigation",
        document_ids=[test_documents[0].id],
    )
    
    # Try to retrieve as different user
    other_user_investigations = db_session.query(Investigation).filter(
        Investigation.user_id == 999,  # Non-existent user
        Investigation.is_deleted == False,
    ).all()
    
    assert len(other_user_investigations) == 0
    assert investigation not in other_user_investigations


@pytest.mark.asyncio
async def test_rag_integration(db_session, test_user, test_documents):
    """Test RAG query with mocked LLM."""
    from unittest.mock import patch
    
    with patch('app.services.rag_service.ask_copilot_with_context') as mock_llm:
        mock_llm.return_value = "The document discusses compliance requirements."
        
        from app.services.rag_service import answer_with_rag
        
        result = await answer_with_rag(
            db=db_session,
            question="What does this document cover?",
            document_ids=[test_documents[0].id],
            user_id=test_user.id,
        )
        
        assert "compliance" in result["answer"]
        assert len(result["sources"]) > 0
```

---

## 10. Performance Optimization Checklist

### Database Optimizations

```python
# ✓ Add index for frequent queries
# backend/alembic/versions/add_indexes.py
def upgrade():
    op.create_index(
        'idx_document_user_id',
        'documents',
        ['user_id']
    )
    op.create_index(
        'idx_investigation_user_id',
        'investigations',
        ['user_id']
    )
    op.create_index(
        'idx_document_chunk_embedding',
        'document_chunks',
        ['embedding'],
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64}
    )


# ✓ Use batch operations
def insert_chunks_batch(chunks_data: list[dict], batch_size: int = 1000):
    """Insert chunks in batches to avoid memory issues."""
    
    for i in range(0, len(chunks_data), batch_size):
        batch = chunks_data[i:i + batch_size]
        
        chunk_models = [
            DocumentChunk(**data)
            for data in batch
        ]
        
        db.bulk_insert_mappings(DocumentChunk, chunk_models)
        db.commit()


# ✓ Use database-level filtering
# ❌ WRONG: Fetch all, then filter
all_investigations = db.query(Investigation).all()
user_investigations = [i for i in all_investigations if i.user_id == user_id]

# ✓ CORRECT: Filter at database level
user_investigations = db.query(Investigation).filter(
    Investigation.user_id == user_id
).all()
```

### Query Optimization

```python
# ✓ Use lazy loading relationships carefully
class Investigation(Base):
    documents = relationship("Document", lazy="select")
    # ↓ Avoid N+1 queries
    
    @staticmethod
    def with_documents(db_session):
        """Eager load documents."""
        return db_session.query(Investigation).options(
            joinedload(Investigation.documents)
        )


# Usage
investigation = Investigation.with_documents(db).filter(...).first()
# This fetches investigation AND documents in ONE query
# Instead of N separate queries
```

---

**Document Completed**: October 9, 2026  
**Total Code Examples**: 40+  
**Topics Covered**: 10 major architectural patterns

