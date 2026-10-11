import re
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.services.copilot_service import ask_copilot_with_context
from app.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/help",
    tags=["Help"],
)

class HelpRequest(BaseModel):
    query: str


_FAQ_ENTRIES = [
    {
        "patterns": [
            r"create.*investigation",
            r"how (do|to).*new investigation",
            r"start.*investigation",
            r"open.*investigation",
        ],
        "answer": (
            "To create an investigation in OpusLex:\n"
            "1. Navigate to the Investigations tab in the left sidebar.\n"
            "2. Click the '+ New' or 'New Investigation' button.\n"
            "3. Enter a title, description, and target jurisdiction.\n"
            "4. Click Create. You can then attach documents, run research queries, and deploy AI compliance agents within the scoped investigation container."
        ),
    },
    {
        "patterns": [
            r"(upload|attach|add).*document",
            r"how (do|to).*upload",
        ],
        "answer": (
            "To upload or attach documents:\n"
            "1. Go to the Documents & Knowledge workspace or the Documents tab inside any specific Investigation.\n"
            "2. Click 'Upload Document' or drag and drop your PDF/text file.\n"
            "3. Once uploaded, the document is automatically indexed and chunked for search, research, and agent analysis."
        ),
    },
    {
        "patterns": [
            r"run.*(agent|investigation agent|compliance agent)",
            r"how (do|to).*use.*agent",
            r"what is an agent",
        ],
        "answer": (
            "To run an AI Compliance Agent in OpusLex:\n"
            "1. Select an active Investigation from the Investigations tab.\n"
            "2. Ensure at least one document is attached to the investigation.\n"
            "3. Navigate to the Agent section inside the investigation.\n"
            "4. Enter your compliance inquiry (e.g., checking specific policy obligations or gaps) and click 'Run Agent'.\n"
            "5. The agent performs strict evidence-grounded analysis and records findings, evidence citations, gaps, and suggested actions."
        ),
    },
    {
        "patterns": [
            r"what is.*investigation",
            r"difference between.*investigation.*research",
            r"investigation vs research",
        ],
        "answer": (
            "An Investigation is a dedicated, secure container for grouping documents, research queries, collaborative comments, and AI agent runs around a specific legal or regulatory matter.\n\n"
            "By contrast, Global Research searches across all accessible documents in your library, while an Investigation strictly confines search, citations, and agents to its attached documents."
        ),
    },
    {
        "patterns": [
            r"google drive",
            r"dropbox",
            r"integration",
            r"connect.*drive",
        ],
        "answer": (
            "External cloud integrations (such as Google Drive and Dropbox) require backend OAuth credentials configured by your administrator. "
            "If credentials are not yet set up, these integrations are marked as 'Not Configured'. You can still upload files directly from your computer using the Document Upload feature."
        ),
    },
]


def match_deterministic_faq(query: str) -> str | None:
    cleaned = query.strip().lower()
    for entry in _FAQ_ENTRIES:
        for pattern in entry["patterns"]:
            if re.search(pattern, cleaned):
                return entry["answer"]
    return None


@router.post("/ask")
async def ask_help(
    request: HelpRequest,
    current_user=Depends(get_current_user),
):
    query = request.query.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Help query cannot be empty.",
        )

    # 1. Deterministic FAQ check for instant, guaranteed accurate product answers
    faq_answer = match_deterministic_faq(query)
    if faq_answer:
        return {"answer": faq_answer, "source": "faq"}

    # 2. Check for general FAQ suggestions intent
    from app.services.help_knowledge import (
        is_faq_suggestion_intent,
        FAQ_SUGGESTIONS_TEXT,
        find_relevant_product_knowledge,
        generate_knowledge_answer,
    )

    if is_faq_suggestion_intent(query):
        return {"answer": FAQ_SUGGESTIONS_TEXT, "source": "faq_suggestions"}

    # 3. Retrieve relevant product knowledge to ground the response
    relevant_docs = find_relevant_product_knowledge(query)
    doc_context = "\n\n".join([f"Topic: {d['title']}\n{d['summary']}" for d in relevant_docs])

    system_prompt = (
        "Explain how to use the OpusLex application. "
        "Answer only from documented/implemented OpusLex functionality. "
        "Do not provide legal advice. "
        "Do not invent features, integrations, permissions, workflows, or capabilities. "
        "When the answer is not supported, say so."
    )

    try:
        answer = await ask_copilot_with_context(
            question=query,
            context=doc_context,
            system_prompt=system_prompt,
            strict_grounding=False,
        )
        return {"answer": answer, "source": "llm"}
    except TimeoutError as te:
        logger.warning(f"Help AI request timed out: {te}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Help AI service timed out while generating a response. Please try again or refer to the Help topics.",
        )
    except RuntimeError as re_err:
        err_msg = str(re_err)
        if "timed out" in err_msg.lower():
            logger.warning(f"Help AI request timed out: {err_msg}")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Help AI service timed out. Please try again later.",
            )
        logger.error(f"Help AI error: {err_msg}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Help AI is temporarily unavailable. Please refer to the Help topics.",
        )
    except Exception as exc:
        logger.error(f"Unexpected error in Help AI: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Help AI is currently unavailable. Please consult the documentation topics.",
        )
