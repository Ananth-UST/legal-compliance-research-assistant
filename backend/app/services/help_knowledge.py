"""
OpusLex Product Knowledge Base and Support Assistant.

Provides accurate, evidence-grounded answers about OpusLex features,
workflows, policies, reports, investigations, documents, research,
and compliance analysis without hallucinating or inventing capabilities.
"""

import re
from typing import Optional

# Structured documentation units representing implemented OpusLex capabilities
KNOWLEDGE_TOPICS = [
    {
        "id": "policies",
        "title": "Policies & Governance Register",
        "keywords": [
            "policy", "policies", "policy register", "governance", "draft policy",
            "active policy", "department policy", "internal policy", "corporate policies"
        ],
        "summary": (
            "Policies in OpusLex are tracked within the Governance & Compliance workspace. "
            "You can manage corporate policies across departments with statuses such as 'Draft' and 'Active'.\n\n"
            "Key capabilities:\n"
            "• Policy Register: View, filter, and track internal corporate policies by department and status.\n"
            "• Statuses: Policies begin in Draft and transition to Active once approved.\n"
            "• Governance Summary: The system aggregates metrics showing total, active, and draft policies.\n"
            "• Compliance Auditing: Policies can be evaluated against external regulations and investigation documents."
        ),
    },
    {
        "id": "reports",
        "title": "Compliance & Governance Reports",
        "keywords": [
            "report", "reports", "compliance report", "governance report", "generate report",
            "interpret report", "risk report", "audit report", "compliance score"
        ],
        "summary": (
            "OpusLex provides a centralized Reports section under Compliance & Governance.\n\n"
            "How to generate & interpret reports:\n"
            "1. Access the Reports tab from the top navigation or sidebar.\n"
            "2. Governance Overview: View aggregate metrics including total policies, active regulations, and overall compliance score.\n"
            "3. Findings Log: Review structured findings from completed AI agent runs across all investigations.\n"
            "4. Risk Indicators: Interpret compliance status categorized into Compliant, Non-Compliant, and High Risk.\n"
            "5. Export & Print: Use the Print/Export button to generate a clean, auditable print-ready compliance summary."
        ),
    },
    {
        "id": "investigations",
        "title": "Investigations & Workflow Containers",
        "keywords": [
            "investigation", "investigations", "create investigation", "new investigation",
            "investigation container", "scope", "case", "matter"
        ],
        "summary": (
            "Investigations are secure, isolated containers in OpusLex designed to group documents, "
            "research queries, notes, and AI agent runs around a specific legal or regulatory matter.\n\n"
            "How to work with investigations:\n"
            "1. Navigate to the Investigations tab and click 'New Investigation'.\n"
            "2. Enter a title, description, and target jurisdiction.\n"
            "3. Attach evidence documents directly to the investigation.\n"
            "4. Run scoped research queries and deploy AI Compliance Agents that reason strictly over the attached documents."
        ),
    },
    {
        "id": "documents",
        "title": "Document Upload & Indexing",
        "keywords": [
            "upload", "document", "documents", "attach document", "upload documents",
            "pdf", "index", "chunk", "embeddings", "knowledge base"
        ],
        "summary": (
            "OpusLex allows you to upload documents directly from your device into the Document Library "
            "or attach them to specific Investigations.\n\n"
            "Processing & Analysis workflow:\n"
            "1. Upload PDF or text documents via the Documents tab or Investigation documents panel.\n"
            "2. The platform extracts raw text, generates semantic chunks, and creates vector embeddings.\n"
            "3. Once processed, documents become instantly searchable via semantic RAG in the Research workspace and available for AI agent analysis."
        ),
    },
    {
        "id": "research",
        "title": "Research Workspace & Global vs Scoped Search",
        "keywords": [
            "research", "global research", "scoped research", "rag", "search documents",
            "query documents", "citation", "citations"
        ],
        "summary": (
            "The Research workspace provides Retrieval-Augmented Generation (RAG) to query documents.\n\n"
            "Difference between Research and Investigations:\n"
            "• Global Research: Searches across all accessible documents and public knowledge in your workspace.\n"
            "• Investigation-Scoped Research: Confines searches and citations exclusively to documents attached to the selected investigation, guaranteeing strict data isolation.\n"
            "• Evidence Grounding: Answers cite source documents with chunk numbers (e.g., [Source: policy.pdf, Chunk: 1])."
        ),
    },
    {
        "id": "agents",
        "title": "AI Compliance Agents & Findings",
        "keywords": [
            "agent", "agents", "compliance agent", "run agent", "agent run",
            "structured findings", "risk score", "conflicts", "evidence gaps", "remediation"
        ],
        "summary": (
            "The Compliance Investigation Agent performs automated, multi-step analysis on documents attached to an investigation.\n\n"
            "Capabilities:\n"
            "1. Strict Grounding: The agent reasons ONLY from the attached documents and refuses to fabricate outside legal facts.\n"
            "2. Structured Output: Produces evidence quotes, document conflicts, evidence gaps, applicable requirements, and suggested actions.\n"
            "3. Risk Heuristic: Computes a preliminary 0–100 risk score and risk level (Low, Medium, High) based on identified gaps and conflicts.\n"
            "4. Auditability: Every run is permanently logged in the investigation's agent run history."
        ),
    },
    {
        "id": "audit",
        "title": "Audit Trail & System Accountability",
        "keywords": [
            "audit", "audit trail", "findings", "system events", "accountability", "logs"
        ],
        "summary": (
            "The Audit & Findings section provides complete transparency into all workspace activities.\n\n"
            "• Audit Trail: Chronological logging of events including document uploads, policy changes, and agent runs.\n"
            "• Findings: Central review of compliance gaps and risks identified by AI agents, including citations back to original document text."
        ),
    },
    {
        "id": "integrations",
        "title": "Cloud Integrations Status",
        "keywords": [
            "integration", "integrations", "google drive", "dropbox", "box", "onedrive", "sharepoint"
        ],
        "summary": (
            "OpusLex supports external cloud integrations, but they require backend OAuth credentials:\n"
            "• Google Drive & Dropbox: Currently marked 'Not Configured' until credentials are provided by your administrator.\n"
            "• Box, OneDrive, SharePoint: Planned for upcoming releases.\n"
            "• Alternative: You can directly upload documents from your computer at any time."
        ),
    },
]


def find_relevant_product_knowledge(query: str) -> list[dict]:
    """Finds matching product documentation topics ranked by relevance."""
    cleaned = query.strip().lower()
    words = set(re.findall(r"\b\w{3,}\b", cleaned))
    matches = []

    for topic in KNOWLEDGE_TOPICS:
        score = 0
        # Check explicit keywords
        for kw in topic["keywords"]:
            if kw in cleaned:
                score += 5
            elif any(w in kw for w in words):
                score += 1
        
        # Check topic title
        if any(w in topic["title"].lower() for w in words):
            score += 2

        if score > 0:
            matches.append((score, topic))

    matches.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in matches]


FAQ_SUGGESTIONS_TEXT = (
    "Here are some common questions you can ask me about OpusLex:\n\n"
    "1. **Policies:** How do I create and manage policies?\n"
    "2. **Reports:** How do I generate and interpret compliance reports?\n"
    "3. **Documents:** How do I upload and analyze documents?\n"
    "4. **Investigations:** How do I create an investigation and run a compliance analysis?\n"
    "5. **Research:** What is the difference between Research and Investigations?\n"
    "6. **AI Agents:** How do I run an AI compliance agent and interpret its findings?\n"
    "7. **Audit & Findings:** Where can I review compliance findings and risk scores?\n\n"
    "Choose a question above or type your own question."
)

_FAQ_INTENT_PATTERNS = [
    r"help.*with.*faq",
    r"show.*faq",
    r"list.*faq",
    r"view.*faq",
    r"^faq(s)?$",
    r"what.*(can|do).*you.*help.*with",
    r"how.*can.*you.*help",
    r"suggest.*(questions|topics|queries)",
    r"what.*(should|can).*i.*ask",
    r"suggested.*questions",
]


def is_faq_suggestion_intent(query: str) -> bool:
    """Checks whether the user is asking for general FAQ suggestions or a list of questions."""
    cleaned = query.strip().lower()
    for pattern in _FAQ_INTENT_PATTERNS:
        if re.search(pattern, cleaned):
            return True
    return False


def generate_knowledge_answer(query: str) -> str:
    """
    Generates a clear, grounded answer from OpusLex product knowledge.
    Handles single-topic, multi-part, FAQ suggestions, or unrecognized questions safely.
    """
    if is_faq_suggestion_intent(query):
        return FAQ_SUGGESTIONS_TEXT

    relevant = find_relevant_product_knowledge(query)

    if not relevant:
        return (
            f"I could not find documented information in OpusLex regarding '{query}'.\n\n"
            "OpusLex specializes in legal and compliance research, investigations, corporate policies, "
            "document analysis, and compliance audit reporting. "
            "Could you clarify which part of OpusLex you would like help with (for example: Policies, Reports, Investigations, Documents, or AI Agents)?"
        )

    # If user asked a multi-part question (e.g. upload documents AND analyze them)
    if len(relevant) >= 2:
        top_two = relevant[:2]
        return (
            f"### {top_two[0]['title']}\n{top_two[0]['summary']}\n\n"
            f"### {top_two[1]['title']}\n{top_two[1]['summary']}"
        )

    # Single primary topic
    top = relevant[0]
    return top["summary"]
