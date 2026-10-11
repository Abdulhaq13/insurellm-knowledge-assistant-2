"""Split a LoadedDocument into retrievable chunks. Owner: Terminal D.

Rules (format-agnostic, nothing specific to any client's documents):
- each Section is chunked on its own, so a chunk never mixes two sections
- every chunk starts with a contextual header "Title > heading > subheading"
- text is split at paragraph, then line, then sentence, then word boundaries, with overlap
- tables are split only between rows, and every table chunk repeats the table header
"""
import re

from answer_engine.config import CHUNK_OVERLAP, CHUNK_SIZE
from answer_engine.schema import Chunk, LoadedDocument, Section

SEPARATORS = ["\n\n", "\n", ". ", " "]
MIN_BODY = 200  # never let a long header squeeze the body below this many characters
TABLE_SEPARATOR_ROW = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def chunk_document(doc: LoadedDocument, client_id: str) -> list[Chunk]:
    chunks = []
    for section in doc.sections:
        if not section.text.strip():
            continue
        header = section_header(doc.title, section.heading_path)
        budget = max(CHUNK_SIZE - len(header) - 2, MIN_BODY)
        bodies = split_table(section.text, budget) if section.kind == "table" else split_text(section.text, budget, CHUNK_OVERLAP)
        for body in bodies:
            chunks.append(
                Chunk(
                    page_content=f"{header}\n\n{body}",
                    metadata={
                        **_scalar_metadata(doc.metadata),
                        "client_id": client_id,
                        "doc_id": doc.doc_id,
                        "source": doc.source,
                        "title": doc.title,
                        "section": " > ".join(section.heading_path) or doc.title,
                        "kind": section.kind,
                        "file_type": doc.file_type,
                        "content_hash": doc.content_hash,
                        "chunk_index": len(chunks),
                    },
                )
            )
    return chunks


def section_header(title: str, heading_path: list[str]) -> str:
    """'Title > heading > subheading', skipping headings that just repeat the title or their parent."""
    parts = [title.strip()] if title.strip() else []
    for heading in heading_path:
        heading = heading.strip()
        if heading and all(heading.lower() != p.lower() for p in parts):
            parts.append(heading)
    return " > ".join(parts)


def split_text(text: str, size: int, overlap: int) -> list[str]:
    """Pack boundary-respecting pieces into chunks of at most `size` chars, repeating up to `overlap` chars."""
    text = text.strip()
    if len(text) <= size:
        return [text]
    pieces = _pieces(text, size, SEPARATORS)
    chunks, current = [], []
    for piece in pieces:
        if current and _length(current) + len(piece) > size:
            chunks.append("".join(current).strip())
            current = _tail(current, overlap)
            while current and _length(current) + len(piece) > size:
                current.pop(0)
        current.append(piece)
    if current:
        chunks.append("".join(current).strip())
    return [c for c in chunks if c]


def split_table(text: str, size: int) -> list[str]:
    """Split a Markdown table between rows; every chunk starts with the header (and separator) rows."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return split_text(text, size, 0)
    header_len = 2 if TABLE_SEPARATOR_ROW.match(lines[1]) else 1
    header, rows = "\n".join(lines[:header_len]), lines[header_len:]
    if not rows:
        return [header]
    budget = max(size - len(header) - 1, 1)
    chunks, current = [], []
    for row in rows:
        # A row longer than the budget becomes its own chunk rather than being cut in half
        if current and _length(current) + len(current) + len(row) > budget:
            chunks.append(current)
            current = []
        current.append(row)
    chunks.append(current)
    return [header + "\n" + "\n".join(rows) for rows in chunks]


def _pieces(text: str, size: int, separators: list[str]) -> list[str]:
    """Break text at the coarsest separator that yields pieces no longer than `size`."""
    if len(text) <= size:
        return [text]
    if not separators:
        return [text[i : i + size] for i in range(0, len(text), size)]
    separator, finer = separators[0], separators[1:]
    parts = text.split(separator)
    pieces = []
    for i, part in enumerate(parts):
        piece = part + (separator if i < len(parts) - 1 else "")
        if piece:
            pieces.extend(_pieces(piece, size, finer))
    return pieces


def _tail(pieces: list[str], overlap: int) -> list[str]:
    """The last <= `overlap` chars of the chunk, starting at a sentence (or else word) boundary."""
    text = "".join(pieces)
    if overlap <= 0 or not text.strip():
        return []
    tail = text[-overlap:]
    if len(tail) < len(text):
        for boundary in ("\n", ". ", " "):
            cut = tail.find(boundary)
            if cut != -1:
                tail = tail[cut + len(boundary) :]
                break
    return [tail] if tail.strip() else []


def _length(pieces: list[str]) -> int:
    return sum(len(p) for p in pieces)


def _scalar_metadata(metadata: dict) -> dict:
    """Chroma only stores str / int / float / bool values."""
    return {k: v for k, v in metadata.items() if isinstance(v, (str, int, float, bool))}
