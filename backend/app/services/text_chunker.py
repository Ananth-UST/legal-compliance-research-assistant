import re


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> list[str]:
    """
    Splits text into chunks preserving sentence and word boundaries.
    Prevents splitting words in half at chunk boundaries.
    """
    if not text or not text.strip():
        return []

    chunks: list[str] = []
    text_len = len(text)
    start = 0

    while start < text_len:
        # Skip leading whitespace at start
        while start < text_len and text[start].isspace():
            start += 1
        if start >= text_len:
            break

        end = min(start + chunk_size, text_len)

        if end < text_len:
            # Try to snap end to the nearest sentence boundary within the last 150 chars
            search_start = max(start, end - 150)
            sentence_break = -1
            for punct in [".\n", ". ", ".\t", "\n\n", "\n"]:
                pos = text.rfind(punct, search_start, end)
                if pos != -1:
                    sentence_break = max(sentence_break, pos + len(punct))

            if sentence_break > start:
                end = sentence_break
            else:
                # Fall back to nearest whitespace before end
                space_break = text.rfind(" ", search_start, end)
                if space_break > start:
                    end = space_break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break

        # Calculate next start point with overlap
        target_start = max(start + 1, end - overlap)
        if target_start < text_len:
            # Prefer snapping to a sentence or paragraph boundary within the overlap window
            search_window = text[target_start:end]
            sentence_match = re.search(r"(\.\s+|\n+)([A-Z0-9\"'•\-])", search_window)
            if sentence_match:
                target_start += sentence_match.start(2)
            elif target_start > 0 and not text[target_start - 1].isspace() and not text[target_start].isspace():
                # Snap target_start to beginning of next word so we never begin mid-word
                next_space = text.find(" ", target_start)
                if next_space != -1 and next_space < end:
                    target_start = next_space + 1
                else:
                    target_start = end

            while target_start < text_len and text[target_start].isspace():
                target_start += 1

            start = max(start + 1, target_start)
        else:
            break

    return chunks
    