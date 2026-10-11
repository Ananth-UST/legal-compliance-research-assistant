import asyncio
import logging
import re
from typing import Optional

from copilot import CopilotClient, SessionEventType
from app.config import settings

logger = logging.getLogger(__name__)

client = CopilotClient()

_client_started = False
client_lock = asyncio.Lock()


async def get_client():
    global _client_started
    async with client_lock:
        if not _client_started:
            await client.start()
            _client_started = True
    return client


def _generate_mock_rag_response(question: str, context: str, strict_grounding: bool) -> str:
    """
    Deterministic mock response generator for test/demo environments.
    Avoids invoking external copilot-runtime or LLM APIs.
    """
    if strict_grounding:
        if not context or "No relevant documents were found" in context:
            return "Based on the provided document context, there is insufficient evidence to answer your question. No matching document evidence was found."

        # Extract citation references from context if present
        source_matches = re.findall(r"Document:\s*([^\n]+).*?Filename:\s*([^\n]+).*?Chunk:\s*(\d+)", context, re.DOTALL)
        if source_matches:
            citations = [f"[Source: {fn.strip()}, Chunk: {chunk}]" for _, fn, chunk in source_matches[:2]]
            citation_str = " ".join(citations)
            return (
                f"Based on the provided document evidence, here is the verified analysis for '{question}':\n\n"
                f"The attached documents provide specific guidance relevant to your inquiry {citation_str}.\n\n"
                f"All statements are strictly grounded in the supplied context."
            )
        return (
            f"Based on the provided documents, here is the analysis for '{question}'. "
            f"All findings reflect the attached material."
        )
    else:
        # Non-strict mode (e.g. general help/knowledge support)
        from app.services.help_knowledge import generate_knowledge_answer
        return generate_knowledge_answer(question)


async def test_copilot() -> str:
    if settings.llm_provider == "mock" or settings.demo_mode:
        return "Copilot connection successful (mock mode active)."

    c = await get_client()

    session = await c.create_session(
        model="auto",
    )

    response_text = ""
    done = asyncio.Event()

    def handle_event(event):
        nonlocal response_text

        if event.type == SessionEventType.ASSISTANT_MESSAGE:
            response_text = event.data.content

        elif event.type == SessionEventType.SESSION_IDLE:
            done.set()

        elif event.type == SessionEventType.SESSION_ERROR:
            error_data = event.data
            response_text = f"SESSION_ERROR: {error_data.message if hasattr(error_data, 'message') else str(error_data)}"
            done.set()

    session.on(handle_event)

    await session.send(
        "Respond with exactly: Copilot connection successful."
    )

    try:
        await asyncio.wait_for(done.wait(), timeout=30.0)
    except asyncio.TimeoutError:
        logger.error("[COPILOT] Request timed out after 30 seconds.")
        raise RuntimeError("Copilot API failed: Request timed out after 30 seconds.")
    finally:
        await session.disconnect()

    if not response_text:
        raise RuntimeError("Copilot API failed: No response received from Copilot.")

    if response_text.startswith("SESSION_ERROR:"):
        raise RuntimeError(f"Copilot API failed: {response_text[14:].strip()}")

    return response_text


async def ask_copilot_with_context(
    question: str,
    context: str,
    system_prompt: str = "You are a legal and compliance research assistant.",
    strict_grounding: bool = True,
) -> str:
    # 1. Provider selection check
    if settings.llm_provider == "mock" or settings.demo_mode:
        logger.info(f"Using mock LLM provider (llm_provider={settings.llm_provider}, demo_mode={settings.demo_mode})")
        return _generate_mock_rag_response(question, context, strict_grounding)

    # 2. Live Copilot execution
    c = await get_client()

    session = await c.create_session(
        model="auto",
        streaming=True,
    )

    response_text = ""
    done = asyncio.Event()

    def handle_event(event):
        nonlocal response_text

        if event.type == SessionEventType.ASSISTANT_MESSAGE:
            response_text = event.data.content

        elif event.type == SessionEventType.SESSION_IDLE:
            done.set()

        elif event.type == SessionEventType.SESSION_ERROR:
            error_data = event.data
            response_text = f"SESSION_ERROR: {error_data.message if hasattr(error_data, 'message') else str(error_data)}"
            done.set()

    session.on(handle_event)

    if strict_grounding:
        grounding_rules = """
Your task is to answer the user's question using ONLY the provided document context.

STRICT GROUNDING RULES:
1. Use only information explicitly supported by the provided context.
2. Do not invent facts, sources, skills, technologies, legal requirements, or interpretations.
3. Preserve the terminology used in the source documents whenever possible.
4. Do not replace a source term with a similar or assumed term.
5. If the context does not contain enough information to answer the question, clearly say that the available documents do not contain enough information.
6. Distinguish between established information and areas of interest or future learning when the source makes that distinction.
7. Every factual statement derived from the documents must include a source citation.
8. Use this exact citation format: [Source: filename, Chunk: number]
9. Only cite sources that actually appear in the provided document context.
10. Do not create or modify filenames, chunk numbers, or source references.
"""
    else:
        grounding_rules = """
Your task is to answer the user's question. If document context is provided, prioritize it and cite your sources using the format [Source: filename, Chunk: number]. 
If the context does not contain enough information to fully answer the question, or if no relevant documents were found, you may answer from your general knowledge.
When answering from general knowledge, you MUST explicitly state that your answer is based on general knowledge and not on specific retrieved evidence. 
For legal, regulatory, and compliance questions, be accurate, communicate uncertainty, and cite authoritative sources if you know them. Do not fabricate citations or external research.
"""

    prompt = f"""
{system_prompt}

{grounding_rules.strip()}

Write the answer clearly and concisely.

User question:
{question}

Document context:
{context}
"""

    logger.info("Sending RAG prompt to Copilot...")

    await session.send(prompt)

    try:
        await asyncio.wait_for(done.wait(), timeout=60.0)
    except asyncio.TimeoutError:
        logger.error("[COPILOT] Request timed out after 60 seconds.")
        raise RuntimeError("Copilot API failed: Request timed out after 60 seconds.")
    finally:
        logger.info("Copilot finished generating the answer.")
        await session.disconnect()

    if not response_text:
        raise RuntimeError("Copilot API failed: No response received from Copilot.")

    if response_text.startswith("SESSION_ERROR:"):
        raise RuntimeError(f"Copilot API failed: {response_text[14:].strip()}")

    return response_text