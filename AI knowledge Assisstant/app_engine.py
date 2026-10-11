"""Chat UI on answer_engine.pipeline, plus a Documents tab to upload, list and delete files.
Run from "AI knowledge Assisstant/": python app_engine.py"""
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

from answer_engine import pipeline
from answer_engine.config import DEFAULT_CLIENT_ID
from answer_engine.loaders import SUPPORTED_EXTENSIONS, NoTextFoundError

load_dotenv(override=True)

CLIENT_ID = DEFAULT_CLIENT_ID  # one client for now; the multi-client platform will choose this per login
MAX_FILE_SIZE = "50mb"
DOCUMENT_COLUMNS = ["Document", "Title", "Type", "Chunks"]
EMPTY_INDEX_HINT = (
    "*No documents indexed yet.* Upload files on the **Documents** tab, or index a whole folder with "
    "`python -m answer_engine.pipeline ingest knowledge-base`."
)


# ---------- chat ----------


def format_sources(chunks) -> str:
    if not chunks:
        return "*No matching documents were found.*"
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.metadata
        section = (meta.get("section") or meta.get("title") or "").replace(" > ", " › ")
        parts.append(f"### {i}. {section}\n`{meta.get('source', '')}`\n\n{chunk.page_content}")
    return "## Sources used\n\n" + "\n\n---\n\n".join(parts)


def chat(history):
    question, prior = history[-1]["content"], history[:-1]
    history = history + [{"role": "assistant", "content": ""}]
    sources = None
    try:
        for answer, chunks in pipeline.stream_answer(question, prior, client_id=CLIENT_ID):
            if sources is None:
                sources = format_sources(chunks)
            history[-1]["content"] = answer
            yield history, sources
    except Exception as error:  # keep the UI alive if retrieval or the LLM fails
        history[-1]["content"] = f"⚠️ Sorry, I couldn't answer that ({type(error).__name__}: {error})."
        yield history, sources or ""


def add_user_message(message, history):
    if not message.strip():
        return message, history
    return "", history + [{"role": "user", "content": message}]


# ---------- documents ----------


def document_rows(documents) -> list[list]:
    return [[d["doc_id"], d.get("title") or "", d.get("file_type") or "", d.get("chunks", 0)] for d in documents]


def refresh_documents():
    """Returns (table rows, delete dropdown, empty-index hint) after any change."""
    documents = pipeline.list_documents(CLIENT_ID)
    doc_ids = [d["doc_id"] for d in documents]
    return (
        document_rows(documents),
        gr.update(choices=doc_ids, value=None),
        gr.update(value=EMPTY_INDEX_HINT, visible=not documents),
    )


def upload_one(path: Path, existing: set[str]) -> str:
    name = path.name
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        return f"❌ **{name}**: unsupported file type. Supported types: {supported}"
    try:
        chunks = pipeline.add_file(path, name, client_id=CLIENT_ID)
    except NoTextFoundError:
        return f"❌ **{name}**: no readable text found, not even with OCR (blank or unreadable scan?)"
    except Exception as error:
        return f"❌ **{name}**: could not read this file ({type(error).__name__}: {error})"
    if chunks == 0:
        return f"⏸ **{name}**: unchanged, this exact file is already indexed"
    count = f"{chunks} chunk{'s' if chunks != 1 else ''}"
    if name in existing:
        return f"🔄 **{name}**: replaced the previous version ({count})"
    return f"✅ **{name}**: added ({count})"


def upload_files(files, progress=gr.Progress()):
    if not files:
        return "*Choose one or more files first.*", None, *refresh_documents()
    existing = {d["doc_id"] for d in pipeline.list_documents(CLIENT_ID)}
    results = []
    for path in progress.tqdm([Path(f) for f in files], desc="Indexing"):
        results.append(upload_one(path, existing))
    return "\n\n".join(results), None, *refresh_documents()


def delete_document(doc_id):
    if not doc_id:
        return "*Nothing deleted.*", *refresh_documents()
    pipeline.remove_document(doc_id, CLIENT_ID)
    return f"🗑️ **{doc_id}** was deleted from the index.", *refresh_documents()


# ---------- layout ----------


def main():
    organization = pipeline.organization_name(CLIENT_ID)
    theme = gr.themes.Soft(font=["Inter", "system-ui", "sans-serif"])
    with gr.Blocks(title=f"{organization} Assistant", theme=theme) as ui:
        gr.Markdown(f"# 🏢 {organization} Assistant\nAsk questions about your documents.")
        empty_hint = gr.Markdown(EMPTY_INDEX_HINT, visible=False)

        with gr.Tab("💬 Chat"):
            with gr.Row():
                with gr.Column(scale=1):
                    chatbot = gr.Chatbot(label="Conversation", height=600, type="messages", show_copy_button=True)
                    message = gr.Textbox(placeholder=f"Ask anything about {organization}...", show_label=False)
                with gr.Column(scale=1):
                    sources = gr.Markdown("*The sources used for each answer will appear here.*", container=True, height=600)

        with gr.Tab("📁 Documents"):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Upload documents\nUploading a file with the same name replaces the old version.")
                    files = gr.File(
                        label=f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
                        file_count="multiple",
                        file_types=sorted(SUPPORTED_EXTENSIONS),
                        type="filepath",
                    )
                    upload_button = gr.Button("Add to index", variant="primary")
                    gr.Markdown("### Delete a document")
                    to_delete = gr.Dropdown(label="Document", choices=[], value=None)
                    delete_button = gr.Button("Delete", variant="stop")
                    status = gr.Markdown()
                with gr.Column(scale=2):
                    gr.Markdown("### Documents in the index")
                    documents = gr.Dataframe(headers=DOCUMENT_COLUMNS, interactive=False, wrap=True)

        refresh_outputs = [documents, to_delete, empty_hint]
        message.submit(add_user_message, [message, chatbot], [message, chatbot]).then(chat, chatbot, [chatbot, sources])
        upload_button.click(upload_files, files, [status, files, *refresh_outputs])
        delete_button.click(
            delete_document,
            to_delete,
            [status, *refresh_outputs],
            js="(doc) => (doc && confirm('Delete \"' + doc + '\" from the index?')) ? doc : null",
        )
        ui.load(refresh_documents, None, refresh_outputs)

    ui.launch(inbrowser=True, max_file_size=MAX_FILE_SIZE)


if __name__ == "__main__":
    main()
