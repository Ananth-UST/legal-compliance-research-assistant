from sqlalchemy.orm import Session

from app.services.copilot_service import ask_copilot_with_context
from app.services.retrieval_service import search_similar_chunks

# Label sequence used for deterministic document naming
_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# =========================================================
# REGULATORY COMPARISON  ─  Map-Reduce Architecture
# =========================================================
#
# PHASE 1 (MAP)
#   For each attached document independently:
#   - retrieve only that document's chunks via search_similar_chunks()
#   - make one focused LLM call covering ONLY that document
#   - produce a structured analysis (education, skills, experience,
#     projects, strengths, gaps, ATS characteristics, citations)
#
# PHASE 2 (REDUCE)
#   After all MAP analyses are produced, make ONE final LLM call.
#   - receives only the N structured analyses, not the raw chunks
#   - explicitly compares every document using the same criteria
#   - never omits a document; never invents information
#
# API RESPONSE SHAPE — unchanged, frontend requires no changes:
#   {
#     "comparison": str,          # final REDUCE text
#     "sources":   {              # per-doc chunk metadata
#       "document_a": [...],
#       "document_b": [...],
#       ...
#     }
#   }
# =========================================================


def _format_chunks(rows) -> str:
    """Format retrieved chunks for embedding in a MAP prompt."""
    if not rows:
        return (
            "(No relevant chunks were retrieved for this document. "
            "Do not fabricate evidence. State that no retrieved evidence "
            "is available for this document.)"
        )
    parts = []
    for row in rows:
        parts.append(f"[Chunk {row['chunk_index']}]\n{row['content']}")
    return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────────
# ATS scoring rubric (transparent, deterministic, applied equally to
# every document so the reduce call can reference consistent scores).
# ──────────────────────────────────────────────────────────────────
_ATS_RUBRIC = """\
ATS PROFILE ASSESSMENT RUBRIC (score each dimension 0-2):
  0 = not found in retrieved evidence
  1 = partially evidenced
  2 = clearly evidenced

Dimensions:
  1. Formatting / readability  — clear sections, standard headings
  2. Section completeness      — education, skills, experience, projects present
  3. Role clarity              — stated objective or role alignment visible
  4. Technical keyword density — relevant technical terms for a software/tech role
  5. Project / experience depth — internship or project detail level
  6. Quantified achievements   — numbers, metrics, outcomes present
  7. Education clarity         — degree, institution, year clearly stated

Sum the 7 dimensions (max 14). Report the numeric subscores and total.
Important limitations:
  - These scores are based only on retrieved text chunks, not the full document.
  - A low score may reflect sparse retrieval, not a poor resume.
  - Do NOT claim scores predict hiring outcome or salary ("CTC").
  - Instead phrase as: "profile alignment with competitive software-engineer roles"."""


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
    evidence = _format_chunks(chunks)

    chunk_count = len(chunks)
    chunk_note = (
        f"{chunk_count} chunk(s) retrieved"
        if chunk_count > 0
        else "0 chunks retrieved — respond with explicit no-evidence statement"
    )

    map_prompt = f"""You are a document analyst. Analyse ONLY the following single document.
Do NOT compare with other documents — that step comes later.

DOCUMENT IDENTITY:
  Label    : Document {label}
  ID       : {doc['id']}
  Filename : {doc['filename']}
  Title    : {doc['title']}
  Jurisdiction: {doc['jurisdiction']}

ORIGINAL QUESTION (for relevance context only):
{question}

RETRIEVAL SUMMARY: {chunk_note}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RETRIEVED EVIDENCE (use ONLY this text)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{evidence}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Use ONLY the retrieved evidence above. Do not invent or infer.
2. Cite every factual statement with [Source: {doc['filename']}, Chunk: N].
3. If the retrieved evidence is empty or irrelevant, say so explicitly
   for each field — do not skip the field.
4. Use "not found in retrieved evidence" rather than claiming the
   field is absent from the full document.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQUIRED OUTPUT STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Produce exactly the following sections. Each section header must appear verbatim.

Document {label} — {doc['filename']} (ID {doc['id']})

EDUCATION
<evidence-based summary or "not found in retrieved evidence">

TECHNICAL SKILLS
<evidence-based summary or "not found in retrieved evidence">

EXPERIENCE / INTERNSHIPS
<evidence-based summary or "not found in retrieved evidence">

PROJECTS
<evidence-based summary or "not found in retrieved evidence">

STRENGTHS (based on retrieved evidence only)
<evidence-based bullet points>

GAPS / WEAKNESSES (based on retrieved evidence only)
<evidence-based bullet points, or "none identified in retrieved evidence">

{_ATS_RUBRIC}

ATS PROFILE SCORE for Document {label}:
  1. Formatting / readability  : [0|1|2] — <one-line justification>
  2. Section completeness      : [0|1|2] — <one-line justification>
  3. Role clarity              : [0|1|2] — <one-line justification>
  4. Technical keyword density : [0|1|2] — <one-line justification>
  5. Project / experience depth: [0|1|2] — <one-line justification>
  6. Quantified achievements   : [0|1|2] — <one-line justification>
  7. Education clarity         : [0|1|2] — <one-line justification>
  
ATS_SCORE: X/14
NOTE: Score reflects only retrieved evidence ({chunk_count} chunk(s)). Not a hiring prediction.
"""

    print(f"[MAP:{label}] Sending to LLM — doc_id={doc['id']}  chunks={chunk_count}")
    analysis = await ask_copilot_with_context(
        question=map_prompt,
        context="Analyse only the single document specified. Do not reference other documents.",
    )
    print(f"[MAP:{label}] Received response — length={len(analysis)}")
    return analysis


async def compare_documents(
    db: Session,
    question: str,
    documents: list[dict],
    limit: int = 5,
) -> dict:
    """
    Map-Reduce document comparison.

    Documents must be an ordered list of dicts:
        [{"id": int, "title": str, "filename": str, "jurisdiction": str}, ...]

    Label assignment is DETERMINISTIC and position-based:
        documents[0]  →  Document A
        documents[1]  →  Document B
        documents[2]  →  Document C
        ...

    Returns the same shape as the previous implementation:
        {"comparison": str, "sources": dict}
    """

    # ──────────────────────────────────────────────────────────────
    # CHECKPOINT 1 — log documents received
    # ──────────────────────────────────────────────────────────────
    print(f"[compare_documents] MAP-REDUCE START — {len(documents)} document(s)")
    for i, doc in enumerate(documents):
        label = _LABELS[i] if i < len(_LABELS) else str(i)
        print(f"  {label} → id={doc['id']}  filename={doc['filename']!r}")

    # ──────────────────────────────────────────────────────────────
    # RETRIEVAL — one independent call per document
    # ──────────────────────────────────────────────────────────────
    from app.services.embedding_service import generate_embedding
    query_embedding = generate_embedding(question)

    per_doc_chunks: list[list] = []
    for doc in documents:
        chunks = search_similar_chunks(
            db=db,
            query=question,
            limit=limit,
            document_ids=[doc["id"]],
            query_embedding=query_embedding,
        )
        per_doc_chunks.append(chunks)
        label = _LABELS[len(per_doc_chunks) - 1]
        print(f"[RETRIEVAL] Document {label} (id={doc['id']}) → {len(chunks)} chunk(s)")

    # ──────────────────────────────────────────────────────────────
    # Build sources dict — keyed "document_a", "document_b", …
    # ──────────────────────────────────────────────────────────────
    sources: dict[str, list[dict]] = {}
    for i, (doc, chunks) in enumerate(zip(documents, per_doc_chunks)):
        label = _LABELS[i] if i < len(_LABELS) else str(i)
        key = f"document_{label.lower()}"
        sources[key] = [
            {
                "document_id": row["document_id"],
                "document_title": row["document_title"],
                "filename": row["document_filename"],
                "chunk": row["chunk_index"],
                "distance": float(row["distance"]),
            }
            for row in chunks
        ]

    # ──────────────────────────────────────────────────────────────
    # PHASE 1 — MAP
    # One focused LLM call per document.  Each call sees ONLY its
    # own chunks.
    #
    # IMPORTANT: executed SEQUENTIALLY, not concurrently.
    # ask_copilot_with_context() uses a module-level singleton
    # CopilotClient that calls client.start() / client.stop() on
    # every invocation.  Running multiple MAP calls concurrently
    # via asyncio.gather() causes the first call to finish to call
    # client.stop(), which shuts down the shared server while other
    # calls are still in flight → SERVER_SHUTTING_DOWN errors.
    # Sequential execution guarantees each call fully completes
    # (including client.stop()) before the next one starts.
    # ──────────────────────────────────────────────────────────────
    print(f"\n[MAP PHASE] Launching {len(documents)} independent analyses (sequential) …")

    map_analyses: list[str] = []
    for i, doc in enumerate(documents):
        label = _LABELS[i] if i < len(_LABELS) else str(i)
        analysis = await _map_single_document(
            label=label,
            doc=doc,
            chunks=per_doc_chunks[i],
            question=question,
        )
        map_analyses.append(analysis)

    print(f"[MAP PHASE] All {len(map_analyses)} analyses complete.")

    # ──────────────────────────────────────────────────────────────
    # [DIAG:MAP_RESULT] — inspect what each MAP call actually returned
    # ──────────────────────────────────────────────────────────────
    import re as _re
    print("\n[DIAG:MAP_RESULT]")
    for i, (doc, analysis) in enumerate(zip(documents, map_analyses)):
        lbl = _LABELS[i] if i < len(_LABELS) else str(i)
        # Extract the exact ATS_SCORE line, e.g. "ATS_SCORE: 12/14"
        total_match = _re.search(r'ATS_SCORE:\s*(\d+)/14', analysis)
        ats_total = total_match.group(0) if total_match else 'NOT FOUND'
        # Extract each dimension score line (looks for "1. … : [N]")
        dim_matches = _re.findall(r'(\d+\.\s+[^:]+):\s*(\[?\d+\]?)', analysis)
        print(f"  label        = {lbl}")
        print(f"  filename     = {doc['filename']!r}")
        print(f"  analysis_len = {len(analysis)}")
        print(f"  ATS TOTAL    = {ats_total}")
        print(f"  ATS dims     = {dim_matches[:7]}")
        print(f"  '/14' in analysis = {'/14' in analysis}")
        print(f"  'ATS' in analysis = {'ATS' in analysis}")
        print()

    # ──────────────────────────────────────────────────────────────
    # PHASE 2 — REDUCE
    # One final LLM call. Receives only the N structured analyses
    # (not the raw chunks). Must explicitly compare every document.
    # ──────────────────────────────────────────────────────────────

    doc_count = len(documents)
    all_labels = ", ".join(
        _LABELS[i] if i < len(_LABELS) else str(i)
        for i in range(doc_count)
    )

    # Build labelled analysis blocks for the reduce prompt
    analysis_blocks: list[str] = []
    for i, (doc, analysis) in enumerate(zip(documents, map_analyses)):
        label = _LABELS[i] if i < len(_LABELS) else str(i)
        analysis_blocks.append(
            f"══════════════════════════════════════════════════════\n"
            f"DOCUMENT {label} ANALYSIS\n"
            f"Filename : {doc['filename']}\n"
            f"ID       : {doc['id']}\n"
            f"══════════════════════════════════════════════════════\n"
            f"{analysis}"
        )
    analyses_block = "\n\n".join(analysis_blocks)

    # Build the per-document identity list for the reduce prompt
    identity_lines: list[str] = []
    for i, doc in enumerate(documents):
        label = _LABELS[i] if i < len(_LABELS) else str(i)
        identity_lines.append(
            f'  Document {label} = {doc["filename"]} (ID {doc["id"]})'
        )
    identity_block = "\n".join(identity_lines)

    reduce_prompt = f"""You are a research assistant performing a final cross-document comparison.
You have received {doc_count} pre-analysed document summaries below.
Your job is to synthesise them into one structured comparison.

ORIGINAL QUESTION:
{question}

DOCUMENT IDENTITY (mandatory — do not alter):
{identity_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

R1. You MUST produce a section for EVERY document: {all_labels}
    Do NOT skip, merge, or omit any document.

R2. Use ONLY information present in the document analyses below.
    Do NOT add external knowledge or invent facts.

R3. When evidence is sparse or absent for a document, say so
    explicitly — do not silently suppress that document.

R4. Do NOT claim that scores predict hiring outcome or actual salary.
    Phrase as "profile alignment with competitive roles" instead.

R5. Do NOT produce an unsupported overall ranking or declare a single winner
    unless the retrieved evidence and rubric scores clearly support it.

R6. Cite sources using [Source: filename, Chunk: N] exactly as they
    appear in the document analyses.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DOCUMENT ANALYSES (input only — do not reproduce verbatim)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{analyses_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REQUIRED OUTPUT STRUCTURE — follow exactly
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

─────────────────────────────────────────────────────
DOCUMENT-BY-DOCUMENT ANALYSIS
─────────────────────────────────────────────────────
Produce one section per document in order {all_labels}.
Each section must be present. Do not merge sections.

For each document include:
- Key education
- Technical skills highlighted
- Experience / internship depth
- Project highlights
- Strengths
- Gaps / weaknesses
- ATS profile score (reproduce from the MAP analysis above)

─────────────────────────────────────────────────────
CROSS-DOCUMENT COMPARISON
─────────────────────────────────────────────────────

SIMILARITIES
List what ALL {doc_count} documents share.

DIFFERENCES
List where they diverge. Attribute each difference to Document A/B/C/…

ATS SCORE SUMMARY TABLE
| Document | Score/14 | Notes |
|----------|----------|-------|
(one row per document; include all {doc_count})
Reminder: scores reflect retrieved evidence only — not a hiring prediction.

PROFILE ALIGNMENT ASSESSMENT
For each document, state how well it aligns with competitive software-engineer
roles based ONLY on the evidence. Do NOT assert a specific hiring probability.

─────────────────────────────────────────────────────
CONCLUSION
─────────────────────────────────────────────────────
A concise, evidence-based conclusion referencing ALL {doc_count} documents ({all_labels}).
State any meaningful differentiators and limitations of this evidence-only comparison.
Do NOT omit any document from the conclusion."""

    # ──────────────────────────────────────────────────────────────
    # [DIAG:REDUCE_INPUT] — confirm what reaches the REDUCE call
    # ──────────────────────────────────────────────────────────────
    print("[DIAG:REDUCE_INPUT]")
    print(f"  number of analyses = {len(map_analyses)}")
    for i, (doc, analysis) in enumerate(zip(documents, map_analyses)):
        lbl = _LABELS[i] if i < len(_LABELS) else str(i)
        total_match = _re.search(r'ATS_SCORE:\s*(\d+)/14', analysis)
        ats_total = total_match.group(0) if total_match else 'NOT FOUND'
        in_block = f"DOCUMENT {lbl} ANALYSIS" in analyses_block
        print(f"  {lbl}: filename={doc['filename']!r}  ATS={ats_total}  analysis_len={len(analysis)}  in_reduce_block={in_block}")
    print(f"  A present in reduce prompt = {'DOCUMENT A ANALYSIS' in reduce_prompt}")
    print(f"  B present in reduce prompt = {'DOCUMENT B ANALYSIS' in reduce_prompt}")
    print(f"  C present in reduce prompt = {'DOCUMENT C ANALYSIS' in reduce_prompt}")
    print(f"  D present in reduce prompt = {'DOCUMENT D ANALYSIS' in reduce_prompt}")
    print(f"  '/14' in reduce prompt     = {'/14' in reduce_prompt}")
    print(f"  'ATS' in reduce prompt     = {'ATS' in reduce_prompt}")
    print(f"  reduce prompt total length = {len(reduce_prompt)}")

    print(f"\n[REDUCE PHASE] Sending reduce prompt — length={len(reduce_prompt)} chars")
    comparison_text = await ask_copilot_with_context(
        question=reduce_prompt,
        context=(
            "Synthesise the pre-analysed document summaries provided. "
            "Every document listed must appear in your output."
        ),
    )
    print(f"[REDUCE PHASE] Response received — length={len(comparison_text)}")

    # ──────────────────────────────────────────────────────────────
    # [DIAG:REDUCE_OUTPUT] — inspect the final REDUCE response
    # ──────────────────────────────────────────────────────────────
    print("\n[DIAG:REDUCE_OUTPUT]")
    print(f"  response length = {len(comparison_text)}")
    for lbl in _LABELS[:doc_count]:
        print(f"  Document {lbl} present = {'Document ' + lbl in comparison_text}")
    print("  exact filenames present/absent:")
    for doc in documents:
        print(f"    {doc['filename']!r}: {doc['filename'] in comparison_text}")
    print(f"  'ATS' present   = {'ATS' in comparison_text}")
    print(f"  '/14' present   = {'/14' in comparison_text}")
    # Check for each expected per-document ATS score (TOTAL line)
    total_matches_in_response = _re.findall(r'TOTAL:\s*\d+/14', comparison_text)
    print(f"  TOTAL:/14 occurrences in response = {len(total_matches_in_response)}: {total_matches_in_response}")
    # Check ATS subscores per doc
    print(f"  'ATS SCORE SUMMARY TABLE' present = {'ATS SCORE SUMMARY TABLE' in comparison_text}")
    # Also dump the first 1000 chars of the response so we can see what it actually starts with
    print(f"\n  === REDUCE RESPONSE HEAD (first 1000 chars) ===\n{comparison_text[:1000]}")
    print(f"  === END HEAD ===")

    return {
        "comparison": comparison_text,
        "sources": sources,
    }


# =========================================================
# RAG  (unchanged — answer_with_rag / build_rag_context)
# =========================================================


def build_rag_context(
    db: Session,
    query: str,
    limit: int = 5,
    document_ids: list[int] | None = None,
    user_id: int | None = None,
) -> tuple[str, list[dict]]:
    from app.services.embedding_service import generate_embedding
    query_embedding = generate_embedding(query)

    if document_ids is not None:
        results = []
        for doc_id in document_ids:
            doc_results = search_similar_chunks(
                db=db,
                query=query,
                limit=limit,
                document_ids=[doc_id],
                user_id=user_id,
                query_embedding=query_embedding,
            )
            results.extend(doc_results)
        # Optional: Sort combined results by distance to prioritize most relevant overall
        results.sort(key=lambda x: x["distance"])
    else:
        results = search_similar_chunks(
            db=db,
            query=query,
            limit=limit,
            document_ids=document_ids,
            user_id=user_id,
            query_embedding=query_embedding,
        )

    if not results:
        return (
            "No relevant documents were found.",
            [],
        )

    context_parts = []
    sources = []

    for result in results:
        context_parts.append(
            f"""Source:
Document: {result["document_title"]}
Filename: {result["document_filename"]}
Chunk: {result["chunk_index"]}

Content:
{result["content"]}
"""
        )

        sources.append(
            {
                "document_id": result["document_id"],
                "document_title": result["document_title"],
                "filename": result["document_filename"],
                "chunk": result["chunk_index"],
                "distance": float(result["distance"]),
            }
        )

    return (
        "\n---\n".join(context_parts),
        sources,
    )


async def answer_with_rag(
    db: Session,
    question: str,
    limit: int = 5,
    document_ids: list[int] | None = None,
    user_id: int | None = None,
    strict_grounding: bool = True,
) -> dict:
    context, sources = build_rag_context(
        db=db,
        query=question,
        limit=limit,
        document_ids=document_ids,
        user_id=user_id,
    )

    answer = await ask_copilot_with_context(
        question=question,
        context=context,
        strict_grounding=strict_grounding,
    )

    return {
        "answer": answer,
        "sources": sources,
    }