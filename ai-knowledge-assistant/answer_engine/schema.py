"""Shared data contract between loaders -> chunking -> index -> retrieval -> generation.
Change these only after agreeing with the owners of the other modules."""
from pydantic import BaseModel, Field


class Section(BaseModel):
    heading_path: list[str] = Field(default_factory=list)  # e.g. ["Carllm", "Pricing", "Basic Tier"]
    text: str
    kind: str = "text"  # "text" or "table" (tables rendered as Markdown)


class LoadedDocument(BaseModel):
    doc_id: str  # stable id within a client, e.g. relative path "products/Carllm.md"
    title: str
    source: str  # shown to users as the citation
    file_type: str  # "pdf", "docx", "xlsx", "csv", "md", "txt", "html", ...
    sections: list[Section]
    content_hash: str  # sha256 of the raw file bytes, used to skip unchanged files
    metadata: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    """`page_content` / `metadata` match LangChain's Document so app.py and evaluation work unchanged."""

    page_content: str  # includes the contextual header, e.g. "Carllm > Pricing\n\n..."
    metadata: dict  # must contain: client_id, doc_id, source, title, section, chunk_index
