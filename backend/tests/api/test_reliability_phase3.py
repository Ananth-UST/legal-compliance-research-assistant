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

    # Test 8: AI Agent inquiry does NOT append Reports content
    res_agent_no_reports = client.post(
        "/api/v1/help/ask",
        json={"query": "How do I run an AI compliance agent and interpret its findings?"},
        headers=owner_headers,
    )
    assert res_agent_no_reports.status_code == 200
    ans_agent = res_agent_no_reports.json()["answer"]
    assert "Reports tab" not in ans_agent
    assert "Compliance & Governance Reports" not in ans_agent
    assert "Compliance Agent" in ans_agent or "AI Compliance Agent" in ans_agent

    # Test 9: Reports question returns Reports content without mixing
    res_rep_clean = client.post(
        "/api/v1/help/ask",
        json={"query": "How do I generate and interpret compliance reports?"},
        headers=owner_headers,
    )
    assert res_rep_clean.status_code == 200
    ans_rep = res_rep_clean.json()["answer"]
    assert "Reports" in ans_rep
    assert "generate & interpret reports" in ans_rep.lower() or "reports tab" in ans_rep.lower()


# 7. AI Compliance Investigation Agent scope & evidence integrity tests
def test_agent_broad_analysis_returns_structured_findings(client, db: Session, test_user: User, owner_headers):
    from app.models.document import Document
    doc = Document(
        title="Corporate Compliance Charter",
        filename="compliance_charter.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Charter Investigation", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (
            "Source:\nDocument: Corporate Compliance Charter\nFilename: compliance_charter.pdf\nChunk: 1\n\nContent: Annual compliance auditing must be documented.",
            [1],
        )
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "What is the compliance status and applicable requirements?"},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"
        assert data["finding"] is not None and len(data["finding"]) > 0
        assert len(data["applicable_requirements"]) >= 1
        assert len(data["evidence"]) >= 1
        assert len(data["evidence_gaps"]) >= 1
        assert len(data["suggested_actions"]) >= 1
        assert len(data["citations"]) >= 1
        assert data["risk_score"] is not None


def test_agent_comprehensive_assessment_request_populates_all_sections(client, db: Session, test_user: User, owner_headers):
    """Verifies that a broad compliance assessment requesting key findings, requirements, evidence, gaps, and actions populates all sections."""
    from app.models.document import Document
    doc1 = Document(
        title="Corporate Compliance Charter",
        filename="compliance_charter.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    doc2 = Document(
        title="Records Management Policy",
        filename="records_policy.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Comprehensive Assessment Inv", user_id=test_user.id, status="open")
    inv.documents.extend([doc1, doc2])
    db.add(inv)
    db.commit()
    db.refresh(inv)

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (
            "Source:\nDocument: Corporate Compliance Charter\nFilename: compliance_charter.pdf\nChunk: 0\n\nContent: Mandatory annual compliance auditing must be documented and submitted.\n\nSource:\nDocument: Records Management Policy\nFilename: records_policy.pdf\nChunk: 1\n\nContent: Records must be preserved for statutory retention periods.",
            [1, 2],
        )
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Please provide a broad compliance assessment including key findings, applicable requirements, supporting evidence, evidence gaps, and recommended actions."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # 1. Key finding is populated
        assert data["finding"] is not None
        assert "compliance assessment" in data["finding"].lower() or "completed" in data["finding"].lower()

        # 2. Applicable requirements populated with citations
        assert len(data["applicable_requirements"]) >= 1
        for req in data["applicable_requirements"]:
            assert req["requirement"] != ""
            assert req["source_document"] in ["compliance_charter.pdf", "records_policy.pdf"]

        # 3. Supporting evidence populated with actual passages
        assert len(data["evidence"]) >= 1
        for ev in data["evidence"]:
            assert ev["claim"] != ""
            assert ev["supporting_text"] != ""
            assert ev["source_document"] in ["compliance_charter.pdf", "records_policy.pdf"]

        # 4. Evidence gaps identified and distinguished from confirmed violations
        assert len(data["evidence_gaps"]) >= 1
        for gap in data["evidence_gaps"]:
            assert gap["description"] != ""
            assert gap["why_it_matters"] != ""
            # Missing evidence is NOT presented as a confirmed violation
            assert "cannot be" in gap["why_it_matters"].lower() or "unverified" in gap["why_it_matters"].lower() or "requires" in gap["why_it_matters"].lower()

        # 5. Proportionate suggested actions provided
        assert len(data["suggested_actions"]) >= 1
        for action in data["suggested_actions"]:
            assert action["action"] != ""
            assert action["rationale"] != ""

        # 6. Citations present
        assert len(data["citations"]) >= 1



def test_agent_narrow_request_only_conflicts(client, db: Session, test_user: User, owner_headers):
    from app.models.document import Document
    doc = Document(
        title="Data Retention Schedule",
        filename="retention_schedule.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Retention Conflict Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (
            "Source:\nDocument: Data Retention Schedule\nFilename: retention_schedule.pdf\nChunk: 0\n\nContent: Retention period is 3 years.\n\nSource:\nDocument: Audit Standard\nFilename: audit_std.pdf\nChunk: 1\n\nContent: Records must be retained for 7 years.",
            [1, 2],
        )
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Identify only conflicts between attached documents. Do not repeat requirements or include an executive summary."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"
        # Executive summary must NOT be present
        assert data["finding"] is None or data["finding"] == ""
        # Only conflicts and the evidence needed to substantiate them
        assert len(data["conflicts"]) == 1
        assert len(data["evidence"]) >= 1
        assert len(data["citations"]) >= 1
        # Non-requested sections must be empty arrays
        assert len(data["evidence_gaps"]) == 0
        assert len(data["applicable_requirements"]) == 0
        assert len(data["suggested_actions"]) == 0
        # Discrepancy distinguished from confirmed contradiction
        conflict = data["conflicts"][0]
        assert "discrepancy" in conflict["description"].lower() or "ambiguity" in conflict["relationship"].lower()


def test_agent_conflict_only_request_with_no_relevant_evidence(client, db: Session, test_user: User, owner_headers):
    from app.models.document import Document
    doc = Document(
        title="Unrelated Document",
        filename="unrelated.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="No Evidence Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = ("No relevant documents were found.", [])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Identify only conflicts between attached documents. Do not repeat requirements or include an executive summary."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"
        # Evidence-grounded refusal, no fabricated conflicts or citations
        assert "no relevant evidence" in data["finding"].lower()
        assert len(data["conflicts"]) == 0
        assert len(data["evidence"]) == 0
        assert len(data["citations"]) == 0


def test_agent_narrow_request_exactly_three_evidence_gaps(client, db: Session, test_user: User, owner_headers):
    from app.models.document import Document
    doc = Document(
        title="Security Controls Manual",
        filename="security_controls.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Gaps Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (
            "Source:\nDocument: Security Controls Manual\nFilename: security_controls.pdf\nChunk: 0\n\nContent: Policy mandates annual training and third-party audit.",
            [1],
        )
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Identify exactly three evidence gaps in the provided documentation. Do not include an executive summary."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"
        assert len(data["evidence_gaps"]) == 3
        # Executive summary excluded
        assert data["finding"] is None or data["finding"] == ""
        # Ensure missing evidence is treated as an evidence gap with why_it_matters, not a confirmed violation
        for gap in data["evidence_gaps"]:
            assert gap["why_it_matters"] != ""
            assert "cannot be" in gap["why_it_matters"].lower() or "requires" in gap["why_it_matters"].lower()
        # Conflicts and requirements are not populated
        assert len(data["conflicts"]) == 0
        assert len(data["applicable_requirements"]) == 0
        assert len(data["suggested_actions"]) == 0


def test_agent_explicit_exclusion_of_executive_summary(client, db: Session, test_user: User, owner_headers):
    from app.models.document import Document
    doc = Document(
        title="Corporate Compliance Charter",
        filename="compliance_charter.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="No Summary Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (
            "Source:\nDocument: Corporate Compliance Charter\nFilename: compliance_charter.pdf\nChunk: 1\n\nContent: Annual compliance auditing must be documented.",
            [1],
        )
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Identify gaps in compliance records. Do not include an executive summary."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"
        assert data["finding"] is None or data["finding"] == ""
        assert len(data["evidence_gaps"]) >= 1


def test_agent_compact_finding_structure(client, db: Session, test_user: User, owner_headers):
    from app.models.document import Document
    doc = Document(
        title="Privacy Notice",
        filename="privacy_notice.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Compact Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (
            "Source:\nDocument: Privacy Notice\nFilename: privacy_notice.pdf\nChunk: 1\n\nContent: Data retention schedule must follow statutory terms.",
            [1],
        )
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Provide a compact finding with citation, rationale, and next action."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"
        assert len(data["citations"]) == 1
        assert len(data["suggested_actions"]) == 1
        assert data["suggested_actions"][0]["rationale"] != ""
        assert data["citations"][0]["source_document"] == "privacy_notice.pdf"
        assert data["citations"][0]["source_section_or_chunk"] == "Chunk 1"


def test_agent_conflict_only_unrelated_chunks_cannot_substantiate_conflict(client, db: Session, test_user: User, owner_headers):
    """
    Confirmed browser observation 1:
    When chunks concern exception approval tickets and incident response procedures
    from the same policy, the agent must NOT fabricate a 3-year vs 7-year retention conflict
    or cite unrelated exception tickets as proof of retention.
    """
    from app.models.document import Document
    doc = Document(
        title="Security Policy",
        filename="security_policy.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Unrelated Chunks Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (
            "Source:\nDocument: Security Policy\nFilename: security_policy.pdf\nChunk: 0\n\nContent: Exception approval tickets must be logged in the ITSM portal within 24 hours.\n\nSource:\nDocument: Security Policy\nFilename: security_policy.pdf\nChunk: 1\n\nContent: Security incident response procedure requires tier-1 connection scanning during initial triage.",
            [1, 2],
        )
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Identify only conflicts between attached documents. Do not repeat requirements or include an executive summary."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Must NOT fabricate a conflict or retention discrepancy
        assert len(data["conflicts"]) == 0
        # Must NOT pair exception approval or incident triage chunks with retention claims
        assert len(data["evidence"]) == 0
        # Must explicitly report the evidence limitation
        assert data["finding"] is not None
        assert "evidence limitation" in data["finding"].lower()
        assert "security_policy.pdf" in data["finding"]
        # Non-requested sections must remain empty
        assert len(data["applicable_requirements"]) == 0
        assert len(data["evidence_gaps"]) == 0
        assert len(data["suggested_actions"]) == 0


def test_agent_broad_assessment_strict_claim_traceability_no_stale_conflicts(client, db: Session, test_user: User, owner_headers):
    """
    Confirmed browser observation 2:
    Broad assessment must ground each requirement and claim directly in its own chunk,
    pair privacy chunks with privacy claims, and must NOT inject an unsolicited retention
    conflict when neither requested nor substantiated by the evidence.
    """
    from app.models.document import Document
    doc1 = Document(
        title="Privacy Workflow Policy",
        filename="privacy_workflow.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    doc2 = Document(
        title="Network Security Standards",
        filename="network_security.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Traceability Broad Inv", user_id=test_user.id, status="open")
    inv.documents.extend([doc1, doc2])
    db.add(inv)
    db.commit()
    db.refresh(inv)

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (
            "Source:\nDocument: Privacy Workflow Policy\nFilename: privacy_workflow.pdf\nChunk: 0\n\nContent: Privacy workflows require documented consent verification before data ingestion.\n\nSource:\nDocument: Network Security Standards\nFilename: network_security.pdf\nChunk: 1\n\nContent: Tier-1 connection scanning must be active during network monitoring.",
            [1, 2],
        )
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Assess the attached documents for compliance. Summarize the key findings, applicable requirements, supporting evidence, evidence gaps, and recommended actions. Distinguish confirmed violations from potential risks and insufficient evidence."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # 1. Broad finding is populated and distinguishes unverified controls from confirmed violations
        assert data["finding"] is not None
        assert "unverified control" in data["finding"].lower() or "evidence gap" in data["finding"].lower()

        # 2. Evidence-to-claim traceability: each claim must match its own quotation
        assert len(data["evidence"]) == 2
        ev1 = next(e for e in data["evidence"] if e["source_document"] == "privacy_workflow.pdf")
        assert ev1["source_section_or_chunk"] == "Chunk 0"
        assert "consent verification" in ev1["supporting_text"].lower()
        assert "privacy" in ev1["claim"].lower() or "consent" in ev1["claim"].lower()
        # Must NOT falsely claim annual compliance audit for privacy chunk
        assert "annual compliance audit" not in ev1["claim"].lower()

        ev2 = next(e for e in data["evidence"] if e["source_document"] == "network_security.pdf")
        assert ev2["source_section_or_chunk"] == "Chunk 1"
        assert "tier-1 connection scanning" in ev2["supporting_text"].lower()
        assert "tier-1" in ev2["claim"].lower() or "scanning" in ev2["claim"].lower()
        # Must NOT falsely claim statutory retention for network chunk
        assert "statutory retention" not in ev2["claim"].lower()

        # 3. Applicable requirements: each requirement matches its own chunk
        assert len(data["applicable_requirements"]) == 2
        req1 = next(r for r in data["applicable_requirements"] if r["source_document"] == "privacy_workflow.pdf")
        assert req1["source_section_or_chunk"] == "Chunk 0"
        assert "privacy" in req1["requirement"].lower() or "data" in req1["requirement"].lower()

        req2 = next(r for r in data["applicable_requirements"] if r["source_document"] == "network_security.pdf")
        assert req2["source_section_or_chunk"] == "Chunk 1"
        assert "tier-1" in req2["requirement"].lower() or "scanning" in req2["requirement"].lower()

        # 4. No unsolicited or fabricated retention conflict
        assert len(data["conflicts"]) == 0

        # 5. Evidence gaps distinguish unverified controls from confirmed violations
        assert len(data["evidence_gaps"]) >= 1
        for gap in data["evidence_gaps"]:
            assert "cannot be verified" in gap["why_it_matters"].lower() or "unverified control" in gap["why_it_matters"].lower()

        # 6. Citations accurately preserved
        assert len(data["citations"]) == 2

        # 7. Test standalone runs retrieval API preserves all references
        runs_res = client.get(
            f"/api/v1/agents/runs?investigation_id={inv.id}",
            headers=owner_headers,
        )
        assert runs_res.status_code == 200
        runs_data = runs_res.json()
        assert len(runs_data) >= 1
        saved_run = runs_data[0]
        assert saved_run["id"] == data["id"]
        assert len(saved_run["evidence"]) == 2
        assert len(saved_run["applicable_requirements"]) == 2
        assert len(saved_run["conflicts"]) == 0


def test_boundary_aware_chunk_text_prevents_mid_word_truncation():
    """
    Verifies that chunk_text respects word and sentence boundaries and does not
    slice words in half (e.g. Data -> ta, Automated -> ted, Zero -> o).
    """
    from app.services.text_chunker import chunk_text

    text = (
        "Data privacy compliance and breach notification workflows must be established across all services. "
        "Automated posture scanning must be integrated for all Tier-1 connections and monitored continuously. "
        "Zero credential hygiene exceptions are permitted, and immediate reporting requirements apply to all staff."
    )
    chunks = chunk_text(text, chunk_size=110, overlap=35)
    assert len(chunks) >= 2
    for chunk in chunks:
        # Every chunk must start with a clean word boundary (no leading fragmented lowercase fragment like "ta", "ted", "o")
        first_word = chunk.split()[0]
        assert first_word not in ["ta", "ted", "o"]
        # The chunk must be a clean slice from text without mid-word cuts
        assert chunk in text or any(chunk.startswith(word) for word in ["Data", "Automated", "Zero", "and", "Tier-1", "Zero"])


def test_agent_truncated_chunks_literal_substring_and_partial_provision(client, db: Session, test_user: User, owner_headers):
    """
    Confirmed browser examples:
    - 'ta privacy compliance and breach notification workflows.'
    - 'ted posture scanning must be integrated for all Tier-1 connections.'
    - 'o credential hygiene, immediate reporting requirements, and usage guidelines.'
    Assert that:
    1. The quotation is a literal, verbatim substring of the source text.
    2. Incomplete fragments are labeled as partial provisions rather than inflated claims.
    3. Requirements are derived directly from the quotation itself, not from unrelated keywords in the chunk.
    """
    from app.models.document import Document
    doc = Document(
        title="Corporate Security Policy",
        filename="security_policy.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Truncated Chunks Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    raw_c0 = "ta privacy compliance and breach notification workflows. The vendor shall notify within 72 hours of discovery."
    raw_c1 = "ted posture scanning must be integrated for all Tier-1 connections. Weekly reports must be filed."
    raw_c2 = "o credential hygiene, immediate reporting requirements, and usage guidelines. Administrative access requires MFA."

    context = (
        f"Source:\nDocument: Corporate Security Policy\nFilename: security_policy.pdf\nChunk: 0\n\nContent: {raw_c0}\n\n"
        f"Source:\nDocument: Corporate Security Policy\nFilename: security_policy.pdf\nChunk: 1\n\nContent: {raw_c1}\n\n"
        f"Source:\nDocument: Corporate Security Policy\nFilename: security_policy.pdf\nChunk: 2\n\nContent: {raw_c2}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1, 2, 3])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Assess the attached documents for compliance. Summarize the key findings, applicable requirements, supporting evidence, evidence gaps, and recommended actions. Distinguish confirmed violations from potential risks and insufficient evidence."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # 1. Quotations are literal substrings of source text
        assert len(data["evidence"]) == 3
        ev0 = data["evidence"][0]
        ev1 = data["evidence"][1]
        ev2 = data["evidence"][2]

        assert ev0["supporting_text"] in raw_c0
        assert ev1["supporting_text"] in raw_c1
        assert ev2["supporting_text"] in raw_c2

        # 2. Incomplete fragments are labeled as partial provisions / fragmentary records
        assert "partial" in ev0["claim"].lower()
        assert "privacy" in ev0["claim"].lower() or "breach" in ev0["claim"].lower()
        # Must NOT inflate into full incident-response program
        assert "incident-response" not in ev0["claim"].lower()

        assert "partial" in ev1["claim"].lower()
        assert "tier-1" in ev1["claim"].lower() or "posture scanning" in ev1["claim"].lower()
        # Must NOT falsely claim annual compliance review for posture scanning chunk
        assert "annual compliance" not in ev1["claim"].lower()

        assert "partial" in ev2["claim"].lower()
        assert "credential hygiene" in ev2["claim"].lower() or "reporting" in ev2["claim"].lower()
        # Must NOT falsely claim annual audit recordkeeping for credential hygiene chunk
        assert "audit-recordkeeping" not in ev2["claim"].lower()
        assert "annual review" not in ev2["claim"].lower()

        # 3. Applicable requirements derived from cited text and labeled as partial provisions
        assert len(data["applicable_requirements"]) == 3
        req0 = data["applicable_requirements"][0]
        req1 = data["applicable_requirements"][1]
        req2 = data["applicable_requirements"][2]

        assert "partial provision" in req0["requirement"].lower()
        assert "privacy" in req0["requirement"].lower() or "breach" in req0["requirement"].lower()

        assert "partial provision" in req1["requirement"].lower()
        assert "tier-1" in req1["requirement"].lower() or "posture scanning" in req1["requirement"].lower()
        assert "annual compliance" not in req1["requirement"].lower()

        assert "partial provision" in req2["requirement"].lower()
        assert "credential hygiene" in req2["requirement"].lower() or "reporting" in req2["requirement"].lower()
        assert "annual review" not in req2["requirement"].lower()


def test_agent_unrelated_chunks_omitted_or_evidence_limitation(client, db: Session, test_user: User, owner_headers):
    """
    Verifies that:
    1. Unrelated non-compliance chunks (e.g. lunch menu) are omitted and cannot substantiate a compliance requirement.
    2. When no retrieved chunks contain compliance provisions, an explicit evidence limitation is returned.
    """
    from app.models.document import Document
    doc = Document(
        title="General Facilities Handbook",
        filename="facilities.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Unrelated Chunks Only Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    unrelated_context = (
        "Source:\nDocument: General Facilities Handbook\nFilename: facilities.pdf\nChunk: 0\n\nContent: The company cafeteria lunch menu is refreshed weekly with vegetarian options available daily.\n\n"
        "Source:\nDocument: General Facilities Handbook\nFilename: facilities.pdf\nChunk: 1\n\nContent: Parking garage access cards are issued by building management on the ground floor."
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (unrelated_context, [1, 2])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Assess the attached documents for compliance. Summarize the key findings, applicable requirements, supporting evidence, evidence gaps, and recommended actions."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Must NOT fabricate compliance requirements or claims for cafeteria menu or parking passes
        assert len(data["applicable_requirements"]) == 0
        assert len(data["evidence"]) == 0
        assert len(data["conflicts"]) == 0

        # Must report explicit evidence limitation
        assert data["finding"] is not None
        assert "evidence limitation" in data["finding"].lower()
        assert "insufficient" in data["finding"].lower() or "missing" in data["finding"].lower()


def test_source_to_chunk_integrity_new_uploads_have_complete_boundaries():
    """
    Verifies source-to-chunk boundary integrity:
    Ensures that when raw document text is chunked using the boundary-aware chunker,
    no chunk begins or ends with mid-word fragments ('ta ', 'ted ', 'o ').
    """
    import re
    from app.services.text_chunker import chunk_text

    raw_text = (
        "SECTION 1. OVERVIEW\n"
        "This specification establishes enterprise operational security safeguards.\n\n"
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

    chunks = chunk_text(raw_text, chunk_size=180, overlap=50)
    assert len(chunks) >= 3

    for i, chunk in enumerate(chunks):
        first_token = chunk.strip().split()[0]
        # Must not be a partial fragment cut in half
        assert first_token not in ["ta", "ted", "o", "es", "ing"], f"Chunk {i} started with partial token: {first_token}"
        # Chunk must begin with a complete word or symbol/header, never punctuation or single-letter remnant
        assert re.match(r"^[A-Za-z0-9\"'•\-]", chunk.strip()), f"Chunk {i} does not start with valid boundary: {repr(chunk[:30])}"
        assert len(first_token) > 1 or first_token.upper() in ["A", "I"], f"Chunk {i} started with orphan single-char token: {first_token}"


def test_stale_existing_chunks_traceability_and_evidence_supported_gaps(client, db: Session, test_user: User, owner_headers):
    """
    Verifies behavior when interacting with existing stale chunks from before the chunker fix:
    1. Displayed quotations remain verbatim substrings of the stored chunk content.
    2. Claims and requirements are strictly derived from the cited snippet (no cross-topic drift).
    3. Truncated chunks are labeled as partial provisions.
    4. Evidence gaps are dynamically derived from retrieved passages and do NOT include generic
       hardcoded vendor-audit or audit-log gaps when unretrieved.
    """
    from app.models.document import Document

    doc_sec = Document(
        title="Information Security Policy",
        filename="POL-SEC-01.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    doc_tpm = Document(
        title="Third Party Risk Standard",
        filename="STD-TPM-03.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Stale Chunks Traceability Inv", user_id=test_user.id, status="open")
    inv.documents.extend([doc_sec, doc_tpm])
    db.add(inv)
    db.commit()
    db.refresh(inv)

    # Simulate existing stale chunks with mid-word truncations
    stale_context = (
        "Source:\nDocument: Third Party Risk Standard\nFilename: STD-TPM-03.pdf\nChunk: 2\n\n"
        "Content: ted posture scanning must be integrated for all Tier-1 connections. Weekly reports must be filed.\n\n"
        "Source:\nDocument: Information Security Policy\nFilename: POL-SEC-01.pdf\nChunk: 3\n\n"
        "Content: o credential hygiene, immediate reporting requirements, and usage guidelines. Administrative access requires MFA."
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (stale_context, [1, 2])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Assess the attached documents for compliance. Summarize the key findings, applicable requirements, supporting evidence, evidence gaps, and recommended actions."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # 1. Quotations must be exact literal substrings of the retrieved context
        for ev in data["evidence"]:
            assert ev["supporting_text"] in stale_context
            # Posture chunk must pair with Tier-1 posture claim
            if "posture scanning" in ev["supporting_text"]:
                assert "tier-1" in ev["claim"].lower() or "posture scanning" in ev["claim"].lower()
                assert "partial provision" in ev["claim"].lower()
            # Credential chunk must pair with credential hygiene claim
            if "credential hygiene" in ev["supporting_text"]:
                assert "credential" in ev["claim"].lower() or "reporting" in ev["claim"].lower()
                assert "partial provision" in ev["claim"].lower()

        # 2. Applicable requirements must match the cited snippets
        for req in data["applicable_requirements"]:
            if "STD-TPM-03.pdf" in req["source_document"]:
                assert "tier-1" in req["requirement"].lower() or "posture scanning" in req["requirement"].lower()
            if "POL-SEC-01.pdf" in req["source_document"]:
                assert "credential" in req["requirement"].lower() or "reporting" in req["requirement"].lower()

        # 3. Evidence gaps must be dynamically derived and reflect the truncated or retrieved controls
        assert len(data["evidence_gaps"]) >= 1
        gap_descs = [g["description"].lower() for g in data["evidence_gaps"]]
        # Since these chunks are truncated, a gap noting truncated text or specific control is generated
        assert any("truncated" in d or "posture" in d or "credential" in d for d in gap_descs)
        # Crucial check: Must NOT include generic vendor-audit gap when vendor data processing is not in the text
        assert not any("third-party vendor data processing audit documentation is not attached" in d for d in gap_descs)


def test_regression_case_1_privacy_workflow_std_prv_02(client, db: Session, test_user: User, owner_headers):
    """
    Case 1: Privacy workflow question scoped to STD-PRV-02.
    - Question: According to STD-PRV-02, what requirements does the document specify for data privacy compliance and breach notification workflows?
    - Must respect STD-PRV-02 scope.
    - Substantive quotation on Chief Privacy Officer oversight must be exact substring.
    - No credential-security gaps or unrelated vendor-risk sections.
    """
    from app.models.document import Document

    doc_prv = Document(
        title="Data Protection and Privacy Standard",
        filename="STD-PRV-02.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="standard",
        jurisdiction="global",
        user_id=test_user.id,
    )
    doc_sec = Document(
        title="Information Security Policy",
        filename="POL-SEC-01.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Case 1 Privacy Workflow Inv", user_id=test_user.id, status="open")
    inv.documents.extend([doc_prv, doc_sec])
    db.add(inv)
    db.commit()
    db.refresh(inv)

    prv_raw = (
        "ACME CORPORATION // GLOBAL SECURITY OPERATIONS CENTER // PAGE 1\n"
        "DOCUMENT ID: STD-PRV-02 // CLASSIFICATION: CONFIDENTIAL\n\n"
        "SECTION 2. ROLES AND RESPONSIBILITIES\n"
        "Chief Privacy Officer: Oversees data privacy compliance and breach notification workflows.\n"
        "Data Stewards: Ensure accuracy and appropriate retention of records."
    )
    context = (
        f"Source:\nDocument: Data Protection and Privacy Standard\nFilename: STD-PRV-02.pdf\nChunk: 0\n\nContent: {prv_raw}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "According to STD-PRV-02, what requirements does the document specify for data privacy compliance and breach notification workflows?"},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Evidence must only cite STD-PRV-02
        assert len(data["evidence"]) >= 1
        for ev in data["evidence"]:
            assert ev["source_document"] == "STD-PRV-02.pdf"
            assert ev["supporting_text"] in prv_raw
            # Substantive quotation: not cover-page header
            assert not ev["supporting_text"].startswith("ACME CORPORATION")

        # Must not have credential-security or vendor-risk gaps
        gap_descs = [g["description"].lower() for g in data["evidence_gaps"]]
        assert not any("credential" in d for d in gap_descs)
        assert not any("vendor" in d for d in gap_descs)

        # Must answer question directly, not generic broad assessment
        assert "broad compliance assessment completed" not in (data["finding"] or "").lower()


def test_regression_case_2_credential_hygiene_pol_sec_01(client, db: Session, test_user: User, owner_headers):
    """
    Case 2: Credential hygiene question scoped to POL-SEC-01.
    - Question: According to POL-SEC-01, what does the policy state about credential hygiene and immediate reporting requirements?
    - Must attribute evidence ONLY to POL-SEC-01 (not STD-PRV-02 or POL-REC-01).
    - Returns actual requested provision.
    - No privacy workflow gaps.
    """
    from app.models.document import Document

    doc_sec = Document(
        title="Information Security Policy",
        filename="POL-SEC-01.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    doc_prv = Document(
        title="Data Protection and Privacy Standard",
        filename="STD-PRV-02.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="standard",
        jurisdiction="global",
        user_id=test_user.id,
    )
    doc_rec = Document(
        title="Records Retention Policy",
        filename="POL-REC-01.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Case 2 Credential Hygiene Inv", user_id=test_user.id, status="open")
    inv.documents.extend([doc_sec, doc_prv, doc_rec])
    db.add(inv)
    db.commit()
    db.refresh(inv)

    sec_raw = (
        "ACME CORPORATION // GLOBAL SECURITY OPERATIONS CENTER // PAGE 1\n"
        "DOCUMENT ID: POL-SEC-01 // CLASSIFICATION: CONFIDENTIAL\n\n"
        "SECTION 5. CREDENTIAL SECURITY\n"
        "Employees & Contractors: Obligated to adhere to credential hygiene, immediate reporting requirements, and usage guidelines.\n"
        "Administrative access requires MFA across all production accounts."
    )
    context = (
        f"Source:\nDocument: Information Security Policy\nFilename: POL-SEC-01.pdf\nChunk: 0\n\nContent: {sec_raw}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "According to POL-SEC-01, what does the policy state about credential hygiene and immediate reporting requirements?"},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Evidence must attribute strictly to POL-SEC-01
        assert len(data["evidence"]) >= 1
        for ev in data["evidence"]:
            assert ev["source_document"] == "POL-SEC-01.pdf"
            assert ev["supporting_text"] in sec_raw
            assert "credential hygiene" in ev["supporting_text"].lower()

        # No privacy workflow gaps
        gap_descs = [g["description"].lower() for g in data["evidence_gaps"]]
        assert not any("privacy" in d for d in gap_descs)
        assert not any("breach notification" in d for d in gap_descs)


def test_regression_case_3_designated_lead_proc_ir_01(client, db: Session, test_user: User, owner_headers):
    """
    Case 3: Incident response question scoped to PROC-IR-01.
    - Question: According to PROC-IR-01, what responsibilities does the designated lead have during security incident response?
    - Must return designated-lead provision.
    - Must reject cover page and appendix fragments as substitutes.
    - No unrelated vendor-risk or privacy recommendations.
    """
    from app.models.document import Document

    doc_ir = Document(
        title="Security Incident Response Procedure",
        filename="PROC-IR-01.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="procedure",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Case 3 Incident Response Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc_ir)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    ir_raw = (
        "ACME CORPORATION // GLOBAL SECURITY OPERATIONS CENTER // PAGE 1\n"
        "DOCUMENT ID: PROC-IR-01 // CLASSIFICATION: CONFIDENTIAL\n\n"
        "SECTION 3. INCIDENT COMMAND RESPONSIBILITIES\n"
        "Incident Commander: Designates the lead managing technical containment and executive communications during active incidents.\n"
        "All containment actions must be logged in the incident management portal."
    )
    context = (
        f"Source:\nDocument: Security Incident Response Procedure\nFilename: PROC-IR-01.pdf\nChunk: 0\n\nContent: {ir_raw}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "According to PROC-IR-01, what responsibilities does the designated lead have during security incident response?"},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Evidence must cite designated lead and containment responsibilities
        assert len(data["evidence"]) >= 1
        ev = data["evidence"][0]
        assert ev["source_document"] == "PROC-IR-01.pdf"
        assert ev["supporting_text"] in ir_raw
        assert not ev["supporting_text"].startswith("ACME CORPORATION")
        assert "designated lead" in ev["claim"].lower() or "lead managing" in ev["supporting_text"].lower() or "containment" in ev["supporting_text"].lower()

        # No unrelated vendor-risk or privacy gaps/actions
        gap_descs = [g["description"].lower() for g in data["evidence_gaps"]]
        assert not any("vendor" in d for d in gap_descs)
        assert not any("privacy" in d for d in gap_descs)


def test_regression_case_4_legal_hold_pol_rec_01(client, db: Session, test_user: User, owner_headers):
    """
    Case 4: Legal hold question scoped to POL-REC-01.
    - Question: According to POL-REC-01, what records or evidence must be preserved during a legal hold?
    - Must return legal hold suspension provision.
    - Must not generate unrelated PIA or breach drill recommendations.
    """
    from app.models.document import Document

    doc_rec = Document(
        title="Records Retention and Legal Hold Policy",
        filename="POL-REC-01.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Case 4 Legal Hold Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc_rec)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    rec_raw = (
        "ACME CORPORATION // GLOBAL SECURITY OPERATIONS CENTER // PAGE 1\n"
        "DOCUMENT ID: POL-REC-01 // CLASSIFICATION: CONFIDENTIAL\n\n"
        "SECTION 6. LEGAL HOLD PROCEDURES\n"
        "REC-HLD-001: Mandatory immediate suspension of regular deletion and automated purging schedules upon issuance of a Legal Hold.\n"
        "All custodian mailboxes, investigation records, and related system logs must be preserved without modification."
    )
    context = (
        f"Source:\nDocument: Records Retention and Legal Hold Policy\nFilename: POL-REC-01.pdf\nChunk: 0\n\nContent: {rec_raw}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "According to POL-REC-01, what records or evidence must be preserved during a legal hold?"},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Evidence must cite REC-HLD-001 / legal hold
        assert len(data["evidence"]) >= 1
        ev = data["evidence"][0]
        assert ev["source_document"] == "POL-REC-01.pdf"
        assert ev["supporting_text"] in rec_raw
        assert not ev["supporting_text"].startswith("ACME CORPORATION")
        assert "legal hold" in ev["claim"].lower() or "legal hold" in ev["supporting_text"].lower()

        # No unrelated PIA or breach drill recommendations
        gap_descs = [g["description"].lower() for g in data["evidence_gaps"]]
        assert not any("privacy impact" in d for d in gap_descs)
        assert not any("breach drill" in d for d in gap_descs)


def test_cross_document_analysis_preserves_multi_document_evidence(client, db: Session, test_user: User, owner_headers):
    """
    Preserve cross-document investigations when explicitly requested.
    - Question: Cross-document analysis: Compare data privacy breach notification workflows in STD-PRV-02 with incident response lead responsibilities in PROC-IR-01.
    - Multi-document evidence must be returned from both documents.
    """
    from app.models.document import Document

    doc_prv = Document(
        title="Data Protection and Privacy Standard",
        filename="STD-PRV-02.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="standard",
        jurisdiction="global",
        user_id=test_user.id,
    )
    doc_ir = Document(
        title="Security Incident Response Procedure",
        filename="PROC-IR-01.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="procedure",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Cross Doc Inv", user_id=test_user.id, status="open")
    inv.documents.extend([doc_prv, doc_ir])
    db.add(inv)
    db.commit()
    db.refresh(inv)

    prv_raw = "Chief Privacy Officer: Oversees data privacy compliance and breach notification workflows."
    ir_raw = "Incident Commander: Designates the lead managing technical containment and executive communications."

    context = (
        f"Source:\nDocument: Data Protection and Privacy Standard\nFilename: STD-PRV-02.pdf\nChunk: 0\n\nContent: {prv_raw}\n\n"
        f"Source:\nDocument: Security Incident Response Procedure\nFilename: PROC-IR-01.pdf\nChunk: 0\n\nContent: {ir_raw}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1, 2])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Cross-document analysis: Compare data privacy breach notification workflows in STD-PRV-02 with incident response lead responsibilities in PROC-IR-01."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Evidence should include citations from both documents
        doc_names = {ev["source_document"] for ev in data["evidence"]}
        assert "STD-PRV-02.pdf" in doc_names
        assert "PROC-IR-01.pdf" in doc_names


def test_evidence_deduplication_across_overlapping_chunks(client, db: Session, test_user: User, owner_headers):
    """
    Test 1: Verify supporting evidence is deduplicated across overlapping chunks.
    If the exact same quotation appears in Chunk 0 and Chunk 1 due to chunk overlap,
    it must appear only once in the final evidence list.
    """
    from app.models.document import Document
    doc = Document(
        title="Data Protection and Privacy Standard",
        filename="STD-PRV-02.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="standard",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Overlap Dedup Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    shared_quote = "Chief Privacy Officer: Oversees data privacy compliance and breach notification workflows."
    c0 = f"SECTION 4. ROLES\n{shared_quote}\nSome preceding context text here."
    c1 = f"{shared_quote}\nSome subsequent context text here in chunk 1."

    context = (
        f"Source:\nDocument: Data Protection and Privacy Standard\nFilename: STD-PRV-02.pdf\nChunk: 0\n\nContent: {c0}\n\n"
        f"Source:\nDocument: Data Protection and Privacy Standard\nFilename: STD-PRV-02.pdf\nChunk: 1\n\nContent: {c1}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1, 2])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "According to STD-PRV-02, what requirements does the document specify for data privacy compliance and breach notification workflows?"},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # The shared quote must not be duplicated
        cpo_quotes = [ev for ev in data["evidence"] if "chief privacy officer" in ev["supporting_text"].lower()]
        assert len(cpo_quotes) == 1, f"Expected exactly 1 quotation for CPO, found {len(cpo_quotes)}"


def test_irrelevant_definitions_excluded_from_supporting_evidence(client, db: Session, test_user: User, owner_headers):
    """
    Test 2: Exclude definitions from supporting evidence when asking for policy requirements.
    Definitions such as 'Restricted Personal Data: Highly sensitive...' should NOT be quoted as requirements.
    """
    from app.models.document import Document
    doc = Document(
        title="Data Protection and Privacy Standard",
        filename="STD-PRV-02.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="standard",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Def Exclusion Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    raw_c0 = (
        "SECTION 3. DEFINITIONS\n"
        "Restricted Personal Data: Highly sensitive personal attributes including financial credentials, health data, and government identifiers.\n"
        "SECTION 4. POLICY / REQUIREMENTS\n"
        "PRV-BR-001: Suspected personal-data breaches must be escalated to Privacy without undue delay."
    )
    context = (
        f"Source:\nDocument: Data Protection and Privacy Standard\nFilename: STD-PRV-02.pdf\nChunk: 0\n\nContent: {raw_c0}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "According to STD-PRV-02, what requirements does the document specify for data privacy compliance and breach notification workflows?"},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Evidence must quote operative provision PRV-BR-001 and NOT the definition
        for ev in data["evidence"]:
            assert "restricted personal data: highly sensitive" not in ev["supporting_text"].lower()
            assert not ev["supporting_text"].startswith("SECTION 3. DEFINITIONS")
        assert any("prv-br-001" in ev["supporting_text"].lower() or "escalated to privacy" in ev["supporting_text"].lower() for ev in data["evidence"])


def test_multiple_relevant_provisions_retrieved_for_policy_query(client, db: Session, test_user: User, owner_headers):
    """
    Test 3: Retrieve all relevant operative provisions, not just the first matching passage.
    """
    from app.models.document import Document
    doc = Document(
        title="Data Protection and Privacy Standard",
        filename="STD-PRV-02.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="standard",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Multi Provision Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    raw_content = (
        "PRV-CL-001: Personal data collection MUST be limited to what is strictly necessary for specified, explicit, and legitimate purposes.\n"
        "PRV-BR-001: Suspected personal-data breaches must be escalated to Privacy without undue delay.\n"
        "Chief Privacy Officer: Oversees data privacy compliance and breach notification workflows."
    )
    context = (
        f"Source:\nDocument: Data Protection and Privacy Standard\nFilename: STD-PRV-02.pdf\nChunk: 0\n\nContent: {raw_content}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "According to STD-PRV-02, what requirements does the document specify for data privacy compliance and breach notification workflows?"},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Multiple distinct operative provisions should be returned
        assert len(data["evidence"]) >= 2
        # Check that both CPO oversight and breach escalation are present
        evidence_texts = [ev["supporting_text"].lower() for ev in data["evidence"]]
        assert any("chief privacy officer" in t for t in evidence_texts)
        assert any("prv-br-001" in t or "escalated to privacy" in t or "prv-cl-001" in t for t in evidence_texts)


def test_pure_policy_questions_omit_generic_evidence_gaps(client, db: Session, test_user: User, owner_headers):
    """
    Test 4: Pure policy questions beginning with 'According to [doc]...' should not generate
    generic operational evidence gaps or audit actions.
    """
    from app.models.document import Document
    doc = Document(
        title="Information Security Policy",
        filename="POL-SEC-01.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="No Gaps Policy Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    raw_sec = (
        "Employees & Contractors: Obligated to adhere to credential hygiene, immediate reporting requirements, and usage guidelines.\n"
        "Security incidents involving Restricted information must be reported to Security within 30 minutes."
    )
    context = (
        f"Source:\nDocument: Information Security Policy\nFilename: POL-SEC-01.pdf\nChunk: 0\n\nContent: {raw_sec}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "According to POL-SEC-01, what does the policy state about credential hygiene and immediate reporting requirements?"},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Policy inquiry should NOT generate generic audit gaps or actions
        assert data["evidence_gaps"] == []
        assert data["suggested_actions"] == []


def test_broad_assessment_distinguishes_missing_evidence_from_violations(client, db: Session, test_user: User, owner_headers):
    """
    Test 5: Broad compliance assessment must distinguish missing operational records from confirmed violations.
    Never present 'not supplied' as 'does not exist' or as a confirmed violation.
    """
    from app.models.document import Document
    doc = Document(
        title="Corporate Security Policy",
        filename="POL-SEC-01.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Broad Assessment Distinction Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    raw_content = "Employees & Contractors: Obligated to adhere to credential hygiene, immediate reporting requirements, and usage guidelines."
    context = (
        f"Source:\nDocument: Corporate Security Policy\nFilename: POL-SEC-01.pdf\nChunk: 0\n\nContent: {raw_content}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "Assess the attached documents for compliance. Summarize key findings, applicable requirements, supporting evidence, evidence gaps, and recommended actions. Distinguish confirmed violations from potential risks and insufficient evidence."},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Finding must state that missing records are unverified controls rather than confirmed violations
        finding_lower = (data["finding"] or "").lower()
        assert "unverified control" in finding_lower or "unverified implementation gaps" in finding_lower
        assert "rather than a confirmed violation" in finding_lower

        # Evidence gaps must also explain that operational evidence has not been supplied/checked
        for gap in data["evidence_gaps"]:
            matters_lower = gap["why_it_matters"].lower()
            assert "unverified control" in matters_lower or "rather than a confirmed violation" in matters_lower


def test_legal_hold_covers_deletion_suspension_and_preserved_records(client, db: Session, test_user: User, owner_headers):
    """
    Test 6: Legal hold query against POL-REC-01 must cover both deletion suspension
    and specific preserved records (custodian mailboxes, investigation records, logs).
    """
    from app.models.document import Document
    doc = Document(
        title="Records Retention and Legal Hold Policy",
        filename="POL-REC-01.pdf",
        file_hash=f"hash_{uuid.uuid4().hex}",
        document_type="policy",
        jurisdiction="global",
        user_id=test_user.id,
    )
    inv = Investigation(title="Legal Hold Full Scope Inv", user_id=test_user.id, status="open")
    inv.documents.append(doc)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    raw_rec = (
        "SECTION 6. LEGAL HOLD PROCEDURES\n"
        "REC-HLD-001: Mandatory immediate suspension of regular deletion and automated purging schedules upon issuance of a Legal Hold.\n"
        "All custodian mailboxes, investigation records, and related system logs must be preserved without modification.\n"
        "Automated storage systems must respect hold flags and block lifecycle deletion routines while a hold is active."
    )
    context = (
        f"Source:\nDocument: Records Retention and Legal Hold Policy\nFilename: POL-REC-01.pdf\nChunk: 0\n\nContent: {raw_rec}"
    )

    with patch("app.services.agent_service.build_rag_context") as mock_rag:
        mock_rag.return_value = (context, [1])
        res = client.post(
            f"/api/v1/agents/investigations/{inv.id}/run",
            json={"question": "According to POL-REC-01, what records or evidence must be preserved during a legal hold?"},
            headers=owner_headers,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "completed"

        # Evidence should cover suspension and/or preserved records
        evidence_texts = [ev["supporting_text"].lower() for ev in data["evidence"]]
        assert any("rec-hld-001" in t or "suspension of regular deletion" in t for t in evidence_texts)
        assert any("custodian mailboxes" in t or "preserved without modification" in t or "hold flags" in t for t in evidence_texts)

        # Finding must describe suspension and preserved record categories
        finding_lower = (data["finding"] or "").lower()
        assert "suspension of regular deletion" in finding_lower or "rec-hld-001" in finding_lower
        assert "custodian mailboxes" in finding_lower or "investigation records" in finding_lower

        # Citations must be traceable
        for cit in data["citations"]:
            assert cit["source_document"] == "POL-REC-01.pdf"
            assert cit["source_section_or_chunk"] == "Chunk 0"

