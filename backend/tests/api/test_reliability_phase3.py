import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import uuid

from app.main import app
from app.database import SessionLocal
from app.models.user import User
from app.models.investigation import Investigation
from app.models.agent_run import AgentRun
from app.routers.auth import create_access_token
from app.routers.help import match_deterministic_faq
from app.services.copilot_service import _generate_mock_rag_response, ask_copilot_with_context


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_user(db: Session):
    user = User(
        email=f"rel_test_{uuid.uuid4().hex[:8]}@example.com",
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
def owner_headers(test_user: User):
    token = create_access_token({"sub": str(test_user.id), "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


# 1. Test deterministic FAQ matches accurately
def test_deterministic_faq_matching():
    res1 = match_deterministic_faq("How do I create an investigation?")
    assert res1 is not None
    assert "Investigations tab" in res1

    res2 = match_deterministic_faq("how to upload a document")
    assert res2 is not None
    assert "Upload Document" in res2

    res3 = match_deterministic_faq("how do I run an agent")
    assert res3 is not None
    assert "Compliance Agent" in res3

    res_unknown = match_deterministic_faq("What is the meaning of life in astrophysics?")
    assert res_unknown is None


# 2. Test Help endpoint with FAQ vs LLM fallback
def test_help_faq_endpoint_response(client, owner_headers):
    # FAQ path
    res = client.post(
        "/api/v1/help/ask",
        json={"query": "How do I create a new investigation?"},
        headers=owner_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "faq"
    assert "Investigations tab" in data["answer"]


@patch("app.routers.help.ask_copilot_with_context")
def test_help_llm_fallback(mock_llm, client, owner_headers):
    mock_llm.return_value = "This is an LLM generated explanation of workspace settings."
    res = client.post(
        "/api/v1/help/ask",
        json={"query": "Explain advanced custom preferences"},
        headers=owner_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["source"] == "llm"
    assert "LLM generated explanation" in data["answer"]


# 3. Test Help endpoint handles timeout explicitly
@patch("app.routers.help.ask_copilot_with_context")
def test_help_timeout_handling(mock_llm, client, owner_headers):
    mock_llm.side_effect = RuntimeError("Copilot API failed: Request timed out after 60 seconds.")
    res = client.post(
        "/api/v1/help/ask",
        json={"query": "Explain obscure regulation outside FAQ"},
        headers=owner_headers,
    )
    assert res.status_code == 504
    assert "timed out" in res.json()["detail"].lower()


# 4. Test mock provider behavior without invoking Copilot CLI
@pytest.mark.asyncio
async def test_mock_provider_deterministic_behavior():
    with patch("app.services.copilot_service.settings") as mock_settings:
        mock_settings.llm_provider = "mock"
        mock_settings.demo_mode = True

        # Strict grounding with context
        context = "Document: Policy A\nFilename: policy_a.pdf\nChunk: 0\nContent: Whistleblower protection is mandatory."
        resp = await ask_copilot_with_context(
            question="What is the policy?",
            context=context,
            strict_grounding=True,
        )
        assert "[Source: policy_a.pdf, Chunk: 0]" in resp

        # Strict grounding with no context
        resp_empty = await ask_copilot_with_context(
            question="What is the policy?",
            context="No relevant documents were found.",
            strict_grounding=True,
        )
        assert "insufficient evidence" in resp_empty.lower()


# 5. Test agent run history loading API
def test_agent_run_history_loading(client, db: Session, test_user: User, owner_headers):
    inv = Investigation(title="History Test Inv", user_id=test_user.id, status="open")
    db.add(inv)
    db.commit()
    db.refresh(inv)

    run1 = AgentRun(
        investigation_id=inv.id,
        user_id=test_user.id,
        question="Check GDPR consent requirement",
        finding="Article 7 consent is missing in data processing contract.",
        status="completed",
        risk_score=75,
        risk_level="Medium",
        evidence=[{
            "claim": "Consent clause absent",
            "source_document": "contract.pdf",
            "source_section_or_chunk": "Clause 4",
            "supporting_text": "Processing may occur without consent.",
        }],
        conflicts=[],
        evidence_gaps=[],
        applicable_requirements=[{
            "requirement": "GDPR Art 7",
            "source_document": "gdpr.pdf",
            "source_section_or_chunk": "Article 7",
        }],
        suggested_actions=[{"action": "Add explicit consent schedule", "rationale": "Ensure compliance"}],
        citations=[],
    )
    db.add(run1)
    db.commit()

    res = client.get(
        f"/api/v1/agents/runs?investigation_id={inv.id}",
        headers=owner_headers,
    )
    assert res.status_code == 200
    runs = res.json()
    assert len(runs) >= 1
    found = next((r for r in runs if r["id"] == run1.id), None)
    assert found is not None
    assert found["question"] == "Check GDPR consent requirement"
    assert found["risk_score"] == 75
    assert len(found["suggested_actions"]) == 1


# 6. Test Help AI Product Knowledge answering broad user questions
def test_help_ai_product_questions(client, owner_headers):
    # Test 1: How do policies work?
    res_pol = client.post(
        "/api/v1/help/ask",
        json={"query": "How do policies work?"},
        headers=owner_headers,
    )
    assert res_pol.status_code == 200
    body_pol = res_pol.json()
    assert "Mock Assistant Response" not in body_pol["answer"]
    assert "Governance & Compliance" in body_pol["answer"] or "Policy Register" in body_pol["answer"]

    # Test 2: How do I generate and interpret a compliance report?
    res_rep = client.post(
        "/api/v1/help/ask",
        json={"query": "How do I generate and interpret a compliance report?"},
        headers=owner_headers,
    )
    assert res_rep.status_code == 200
    body_rep = res_rep.json()
    assert "Mock Assistant Response" not in body_rep["answer"]
    assert "Reports" in body_rep["answer"]

    # Test 3: How do I upload documents and analyze them?
    res_up = client.post(
        "/api/v1/help/ask",
        json={"query": "How do I upload documents and analyze them?"},
        headers=owner_headers,
    )
    assert res_up.status_code == 200
    body_up = res_up.json()
    assert "Mock Assistant Response" not in body_up["answer"]
    assert "Document" in body_up["answer"]

    # Test 4: What is the difference between Research and an Investigation?
    res_diff = client.post(
        "/api/v1/help/ask",
        json={"query": "What is the difference between Research and an Investigation?"},
        headers=owner_headers,
    )
    assert res_diff.status_code == 200
    body_diff = res_diff.json()
    assert "Mock Assistant Response" not in body_diff["answer"]
    assert "Investigation" in body_diff["answer"]
    assert "Research" in body_diff["answer"]

    # Test 5: Unfamiliar product question
    res_unfam = client.post(
        "/api/v1/help/ask",
        json={"query": "Can I book airline tickets in OpusLex?"},
        headers=owner_headers,
    )
    assert res_unfam.status_code == 200
    body_unfam = res_unfam.json()
    assert "Mock Assistant Response" not in body_unfam["answer"]
    assert "could not find documented information" in body_unfam["answer"].lower()

    # Test 6: General FAQ suggestions intent variations
    faq_queries = [
        "Help me with the FAQs",
        "show FAQs",
        "help me with FAQs",
        "what can you help me with?",
        "suggest questions",
    ]
    for fq in faq_queries:
        res_faq = client.post(
            "/api/v1/help/ask",
            json={"query": fq},
            headers=owner_headers,
        )
        assert res_faq.status_code == 200
        ans = res_faq.json()["answer"]
        assert "1. **Policies:** How do I create and manage policies?" in ans
        assert "2. **Reports:** How do I generate and interpret compliance reports?" in ans
        assert "3. **Documents:** How do I upload and analyze documents?" in ans
        assert "4. **Investigations:** How do I create an investigation and run a compliance analysis?" in ans
        assert "5. **Research:** What is the difference between Research and Investigations?" in ans
        assert "6. **AI Agents:** How do I run an AI compliance agent and interpret its findings?" in ans
        assert "7. **Audit & Findings:** Where can I review compliance findings and risk scores?" in ans
        assert "Choose a question above or type your own question." in ans

    # Test 7: Confirm specific question about adding policies or documents still gives detailed answers
    res_add_pol = client.post(
        "/api/v1/help/ask",
        json={"query": "How do I add new policies or compliance documents to OpusLex?"},
        headers=owner_headers,
    )
    assert res_add_pol.status_code == 200
    ans_add_pol = res_add_pol.json()["answer"]
    assert "To upload or attach documents:" in ans_add_pol
    assert "Documents" in ans_add_pol
    assert "Mock Assistant Response" not in ans_add_pol


