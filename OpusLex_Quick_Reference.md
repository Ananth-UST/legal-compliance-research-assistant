# OpusLex Quick Reference Guide

## 1. Key Dependencies & Versions

### Backend (Python)
```
fastapi==0.141.1           # Web framework
python==3.12+              # Runtime
sqlalchemy==2.0.52         # ORM
alembic==1.19.1            # Migrations
pgvector==0.5.0            # Vector DB extension
sentence-transformers==6.0.1  # Embeddings (all-MiniLM-L6-v2)
github-copilot-sdk==1.0.13 # LLM provider
PyMuPDF==1.28.2            # PDF extraction
pydantic==2.13.5           # Data validation
uvicorn==0.52.4            # ASGI server
```

### Frontend (Node.js)
```
react==19.2.8              # UI framework
typescript==6.0.2          # Language
vite==8.2.2                # Build tool
tailwindcss==4.3.3         # Styling
i18next==26.4.2            # Localization
lucide-react==1.43.0       # Icon library
```

---

## 2. Core Services Map

### Backend Services (app/services/)
```
1. rag_service.py           → Map-Reduce document comparison
2. agent_service.py         → Autonomous agent execution
3. copilot_service.py       → GitHub Copilot API wrapper
4. retrieval_service.py     → Vector similarity search
5. embedding_service.py     → Semantic embeddings
6. pdf_extractor.py         → PDF text extraction
7. text_chunker.py          → Semantic chunking
8. chunk_service.py         → Chunk management
9. email_service.py         → Email & SMS notifications
```

### Data Models (app/models/)
```
1. user.py                  → User accounts & authentication
2. document.py              → Document metadata & tracking
3. document_chunk.py        → Semantic chunks + embeddings (384-dim)
4. investigation.py         → Incident investigations
5. investigation_document.py → Document attachment (M2M)
6. investigation_query.py    → Questions & answers within investigation
7. investigation_comment.py  → Discussion threads
8. compliance.py            → Compliance frameworks
9. regulation.py            → Regulatory requirements
10. policy.py               → Internal policies
11. knowledge_post.py       → Knowledge base entries
12. agent_run.py            → Agent execution history
13. research.py             → Research projects
14. integration.py          → Third-party service integrations
15. base.py                 → Base model with common fields
```

---

## 3. API Router Organization

### Router Endpoints Summary

| Router | Count | Primary Operations |
|--------|-------|-------------------|
| auth.py | ~4 | login, register, verify, refresh |
| document.py | ~6 | upload, list, delete, retrieve, chunk management |
| compliance.py | ~5 | CRUD operations, rule matching |
| research.py | ~4 | create, track, update research |
| investigations.py | ~7 | create, query, compare, store results |
| agent.py | ~5 | execute, monitor, log agent runs |
| knowledge.py | ~5 | post, search, retrieve KB entries |
| workspace.py | ~4 | workspace management, isolation |
| policies.py | ~4 | policy CRUD, querying |
| regulations.py | ~4 | regulation management |
| audit.py | ~5 | audit logging, retrieval |
| governance.py | ~4 | approval workflows |
| help.py | ~3 | FAQ, guidance |
| integrations.py | ~6 | service integration setup |
| data.py | ~3 | utility endpoints |
| rag.py | ~3 | RAG operations |
| mcp.py | ~2 | MCP bridge |

**Total**: ~80+ API endpoints across 17 routers

---

## 4. Database Schema at a Glance

### User & Workspace Isolation
```
User
├── user_id (PK)
├── email
├── password_hash
├── role (admin, analyst, viewer)
└── workspace_id (FK)

Workspace
├── workspace_id (PK)
├── name
└── created_at
```

### Document Processing Pipeline
```
Document
├── document_id (PK)
├── user_id (FK)
├── filename
├── title
├── content_hash (deduplication)
├── jurisdiction
└── created_at

DocumentChunk
├── chunk_id (PK)
├── document_id (FK)
├── content (text)
├── embedding (pgvector, 384-dim)
├── chunk_index
├── distance (cosine similarity)
└── created_at
```

### Investigation Workflow
```
Investigation
├── investigation_id (PK)
├── user_id (FK)
├── title
├── status (open, in-progress, closed)
└── created_at

InvestigationDocument (M2M)
├── document_id (FK)
└── investigation_id (FK)

InvestigationQuery
├── query_id (PK)
├── investigation_id (FK)
├── question
├── answer (LLM response)
├── sources (metadata)
└── created_at

InvestigationComment
├── comment_id (PK)
├── investigation_id (FK)
├── user_id (FK)
├── text
└── created_at
```

### Compliance & Governance
```
Compliance
├── compliance_id (PK)
├── framework_name
├── requirements (JSON)

Regulation
├── regulation_id (PK)
├── jurisdiction
├── title
├── requirements

Policy
├── policy_id (PK)
├── title
├── content
├── version

KnowledgePost
├── post_id (PK)
├── title
├── content
├── author_id (FK)
```

---

## 5. Performance Metrics

### Latency Profile
```
Component                      | Time    | % of Total
---------------------------------------------------
Embedding Generation           | 600-1600ms | 2-5%
Vector Retrieval (HNSW)       | 22ms       | <1%
Vector Retrieval (pre-opt)    | 84ms       | <1%
LLM Context Construction      | <5ms       | <1%
LLM Generation (Copilot)      | ~30,269ms  | 98%+
Database Operations           | <5ms       | <1%
```

### Vector Search Optimization
- **Before**: 84ms (sequential scan)
- **After**: 22ms (HNSW index)
- **Improvement**: -73% latency

### Database Indexes
```
DocumentChunk:
  - embedding (HNSW, m=16, ef_construction=64)
  - document_id (B-tree)
  - chunk_index (B-tree)

Document:
  - user_id (B-tree, multi-tenant isolation)
  - content_hash (B-tree, deduplication)
```

---

## 6. Frontend Component Structure

### Page Components
```
App.tsx (Main router)
├── Dashboard.tsx          # Home page with analytics
├── Investigations.tsx     # Investigation management
├── Research.tsx           # Research tracking
├── Compliance.tsx         # Compliance queries
├── Agents.tsx             # Agent execution UI
├── Policies.tsx           # Policy management
├── Regulations.tsx        # Regulation browsing
├── Audit.tsx              # Audit trail
├── Governance.tsx         # Approval workflows
├── Knowledge.tsx          # KB search & posting
├── Help.tsx               # FAQ & guidance
├── Integrations.tsx       # Service integration
├── Auth.tsx               # Login/register
└── Reports.tsx            # Report generation
```

### Shared Components
```
OpusLexBrand.tsx       # Theme & branding
SegmentedControl.tsx   # Toggle controls
GoogleDrivePicker.tsx  # File selection
```

### Internationalization
```
i18n/locales/
├── en.json             # English strings
└── es.json             # Spanish strings
```

---

## 7. Critical Workflow Sequences

### Document Upload Flow
```
1. POST /documents (FormData with PDF)
2. File validation (size, type, user auth)
3. PyMuPDF extraction → text content
4. Text chunker → semantic chunks
5. Sentence Transformers → 384-dim embeddings
6. Store DocumentChunk records (batch insert)
7. HNSW index automatically updated
8. Return: document_id, chunk_count, embedding_time
```

### RAG Query Execution
```
1. POST /rag/ask {question, document_ids?, user_id}
2. Embed question (Sentence Transformers)
3. Vector search: SELECT * FROM chunks 
                  ORDER BY embedding <-> query_embedding
                  LIMIT 5
4. Format retrieved chunks as context
5. Call Copilot API with question + context
6. Wait up to 45 seconds for response
7. Return: {answer, sources: [{doc_id, filename, chunk, distance}]}
```

### Map-Reduce Comparison
```
1. GET /rag/compare {investigation_id, document_ids}
2. For each document (sequential):
   a. Retrieve document-specific chunks
   b. Create MAP prompt with only that document's evidence
   c. Call Copilot API
   d. Store result in memory
3. Create REDUCE prompt with all MAP results
4. Call Copilot API once for final comparison
5. Return: {comparison_text, sources}
```

---

## 8. Authentication & Authorization

### Auth Flow
```
1. POST /auth/login {email, password}
2. Verify credentials against password_hash
3. Generate JWT token (python-jose)
4. Return: {access_token, user: {id, email, role}}
5. Client stores token in localStorage
6. Subsequent requests: Authorization: Bearer <token>
```

### Role-Based Access Control
```
Roles:
- admin       → Full platform access
- analyst     → Create/query investigations, RAG
- viewer      → Read-only access

Enforcement:
- Every endpoint checks user_id from JWT
- Workspace_id filters prevent cross-tenant access
- Role checks in router dependencies
```

---

## 9. Error Handling Patterns

### Common Error Responses
```
400 Bad Request
{
  "detail": "Invalid PDF format",
  "error_code": "PDF_PARSE_ERROR"
}

401 Unauthorized
{
  "detail": "Invalid or expired token",
  "error_code": "AUTH_FAILED"
}

403 Forbidden
{
  "detail": "Access denied to this investigation",
  "error_code": "PERMISSION_DENIED"
}

404 Not Found
{
  "detail": "Document not found",
  "error_code": "RESOURCE_NOT_FOUND"
}

500 Internal Server Error
{
  "detail": "LLM timeout after 45 seconds",
  "error_code": "LLM_TIMEOUT"
}
```

---

## 10. Environment Variables

### Backend (.env)
```
DATABASE_URL=postgresql://user:pass@localhost/opuslex
COPILOT_API_KEY=<github-copilot-token>
SECRET_KEY=<jwt-secret-key>
GOOGLE_CLIENT_ID=<google-oauth-id>
TWILIO_ACCOUNT_SID=<twilio-sid>
TWILIO_AUTH_TOKEN=<twilio-token>
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=<email>
SMTP_PASSWORD=<password>
```

### Frontend (.env.local)
```
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_APP_NAME=OpusLex
```

---

## 11. Testing Strategy

### Test Infrastructure
```
Framework: pytest + pytest-asyncio
Backend: backend/tests/ directory
Test files:
  - test_investigation_lifecycle.py   (E2E test)
  - test_compare.py                   (Comparison test)

Run tests:
  pytest                              # All tests
  pytest -v                           # Verbose
  pytest backend/tests/test_*.py      # Specific module
```

### Recommended Test Coverage
- [ ] API endpoint tests (all routers)
- [ ] Service layer unit tests
- [ ] Database integration tests
- [ ] RAG pipeline tests
- [ ] Security/auth tests
- [ ] Multi-tenancy tests
- [ ] Error handling tests

---

## 12. Deployment Checklist

### Pre-Deployment
- [ ] Review all environment variables
- [ ] Database migrations run successfully
- [ ] PDF extraction tested with sample documents
- [ ] Copilot API credentials validated
- [ ] Frontend build completes without errors
- [ ] All tests pass
- [ ] Security scan completed (OWASP)

### Infrastructure
- [ ] PostgreSQL with pgvector extension running
- [ ] GitHub Copilot CLI installed & authenticated
- [ ] HTTPS/TLS certificates configured
- [ ] Redis (optional, for caching)
- [ ] Load balancer configured
- [ ] CDN setup for static assets

### Monitoring & Logging
- [ ] Application logging (stderr to CloudWatch/ELK)
- [ ] Error tracking (Sentry, DataDog)
- [ ] APM instrumentation (New Relic, Datadog)
- [ ] Database monitoring (slow query logs)
- [ ] Copilot API monitoring (latency, errors)

### Security
- [ ] Secrets management (AWS Secrets Manager)
- [ ] Network segmentation (VPC, security groups)
- [ ] WAF rules configured
- [ ] Audit logging enabled
- [ ] Data encryption at rest & in transit

---

## 13. Common Development Tasks

### Add a New Endpoint
```python
# 1. Create schema (app/schemas/my_feature.py)
from pydantic import BaseModel
class MyRequest(BaseModel):
    query: str

class MyResponse(BaseModel):
    result: str
    sources: list

# 2. Create router (app/routers/my_router.py)
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/my-feature", tags=["my-feature"])

@router.post("/query", response_model=MyResponse)
async def my_endpoint(
    request: MyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # Implementation
    pass

# 3. Include router in main.py
app.include_router(my_router.router)

# 4. Add tests
# 5. Document in swagger
```

### Add Database Model
```python
# 1. Create model (app/models/my_model.py)
from app.models.base import Base
from sqlalchemy import Column, Integer, String, ForeignKey

class MyModel(Base):
    __tablename__ = "my_models"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    content = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# 2. Create migration
alembic revision --autogenerate -m "Add MyModel table"

# 3. Apply migration
alembic upgrade head
```

### Add Frontend Component
```typescript
// 1. Create component (frontend/src/components/MyComponent.tsx)
import React from 'react';
import { useTranslation } from 'react-i18next';

export const MyComponent: React.FC = () => {
  const { t } = useTranslation();
  
  return <div>{t('my.component.label')}</div>;
};

// 2. Add i18n strings (frontend/src/i18n/locales/en.json)
{
  "my": {
    "component": {
      "label": "My Component Label"
    }
  }
}

// 3. Import in App.tsx or parent component
// 4. Add route if needed
```

---

## 14. Troubleshooting Guide

### Common Issues

**Issue**: "Copilot API timeout"
- **Cause**: LLM taking >45 seconds
- **Fix**: Check Copilot service status, reduce context size, increase timeout

**Issue**: "No relevant documents found"
- **Cause**: Poor embeddings or wrong document
- **Fix**: Check embedding model, verify document chunks, try simpler query

**Issue**: "User data leaking across tenants"
- **Cause**: Missing user_id filter
- **Fix**: Add user_id to all db queries, check workspace scoping

**Issue**: "PDF extraction fails"
- **Cause**: Corrupted PDF or unsupported format
- **Fix**: Validate PDF file, check PyMuPDF installation, try different PDF

**Issue**: "Vector search slow"
- **Cause**: HNSW index missing or outdated
- **Fix**: Check index exists, reindex if corrupted, verify migration applied

**Issue**: "Database migrations won't apply"
- **Cause**: Alembic state mismatch
- **Fix**: Check current migration: `alembic current`, debug heads: `alembic heads`

---

## 15. Learning Path for New Developers

### Week 1: Setup & Orientation
1. Clone repository
2. Set up backend (Python environment, PostgreSQL, Copilot)
3. Set up frontend (Node.js, npm install)
4. Run both locally
5. Read README.md & architecture docs
6. Explore database schema

### Week 2: Understand Core Flows
1. Trace document upload → embedding flow
2. Understand RAG query execution
3. Study Map-Reduce comparison logic
4. Review authentication & authorization
5. Examine investigation workflow

### Week 3: Make Your First Contribution
1. Add a simple API endpoint
2. Add frontend component for it
3. Write unit tests
4. Submit PR with documentation

### Week 4+: Deeper Topics
1. Study vector search optimization
2. Learn Copilot API integration
3. Understand multi-tenancy scoping
4. Explore agent execution patterns
5. Study performance bottlenecks

---

**Last Updated**: October 9, 2026  
**Project**: OpusLex - Legal & Compliance Research Assistant  
**Version**: 1.0.0

