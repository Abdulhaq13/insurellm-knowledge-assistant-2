"""Chat UI on answer_engine.pipeline, plus a Documents tab to upload, list and delete files.
Run from "ai-knowledge-assistant/": python app.py"""
import re
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

from answer_engine import pipeline
from answer_engine.config import DEFAULT_CLIENT_ID
from answer_engine.loaders import SUPPORTED_EXTENSIONS, NoTextFoundError

load_dotenv(override=True)

CLIENT_ID = DEFAULT_CLIENT_ID  # one client for now; the multi-client platform will choose this per login
MAX_FILE_SIZE = "50mb"
INPUT_PLACEHOLDER = f"Ask anything about {pipeline.organization_name(CLIENT_ID)}..."
ANSWERING_PLACEHOLDER = "Answering… you can ask the next question when this answer is finished."
DOCUMENT_COLUMNS = ["Document", "Title", "Type", "Chunks"]
EMPTY_INDEX_HINT = (
    "*No documents indexed yet.* Upload files on the **Documents** tab, or index a whole folder with "
    "`python -m answer_engine.pipeline ingest data/insurellm`."
)
# The answer prompt says "you don't have that information in the available documents" when nothing answers
# the question. Partial answers start with facts, so only the first sentence is checked, and it must also talk
# about the information/documents ("Carllm is not available in Europe" is a real answer, not a refusal).
NO_ANSWER = re.compile(
    r"\b(don['’]t|do not|doesn['’]t|does not) (have|contain|include|mention)\b|\bno (information|details|data|mention)\b"
    r"|\b(isn['’]t|is not|aren['’]t|are not|not) (available|mentioned|provided|included|specified)\b",
    re.IGNORECASE,
)
ABOUT_SOURCES = re.compile(r"\b(information|details|documents?|excerpts?|context|sources?|records?)\b", re.IGNORECASE)
# Images in Markdown/HTML make the browser fetch their URL, which tells that server who looked (and an answer
# could carry document text in the URL). Answers never need images, so they are removed before display.
IMAGES = re.compile(
    r"!\[[^\]]*\]\([^)]*\)|!\[[^\]]*\]\[[^\]]*\]|<(img|video|audio|source|iframe|embed|object|picture)\b[^>]*>",
    re.IGNORECASE,
)


# ---------- chat ----------


def is_no_answer(answer: str) -> bool:
    first_sentence = re.split(r"(?<=[.!?])\s", answer.strip(), maxsplit=1)[0]
    return bool(NO_ANSWER.search(first_sentence) and ABOUT_SOURCES.search(first_sentence))


def remove_images(text: str) -> str:
    return IMAGES.sub("", text)


def plain_text(text: str) -> str:
    """Show uploaded text as-is in a code block, so nothing in it (images, links, HTML) is rendered."""
    fence = "`" * max(3, max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    return f"{fence}text\n{text}\n{fence}"


def format_sources(chunks, used: bool = True) -> str:
    if not chunks:
        return "*No matching documents were found.*"
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.metadata
        section = remove_images(meta.get("section") or meta.get("title") or "").replace(" > ", " › ")
        source = remove_images(meta.get("source", "")).replace("`", "'")
        parts.append(f"### {i}. {section}\n`{source}`\n\n{plain_text(chunk.page_content)}")
    heading = "## Sources used" if used else "## Closest matches (not used in the answer)"
    return f"{heading}\n\n" + "\n\n---\n\n".join(parts)


def chat(history):
    if not history or history[-1]["role"] != "user":  # empty submit: nothing new to answer
        return
    question, prior = history[-1]["content"], history[:-1]
    history = history + [{"role": "assistant", "content": ""}]
    sources = None
    try:
        for answer, chunks in pipeline.stream_answer(question, prior, client_id=CLIENT_ID):
            if sources is None:
                sources = format_sources(chunks)
            history[-1]["content"] = remove_images(answer)
            yield history, sources
        if chunks and is_no_answer(answer):
            yield history, format_sources(chunks, used=False)
    except Exception as error:  # keep the UI alive if retrieval or the LLM fails
        history[-1]["content"] = f"⚠️ Sorry, I couldn't answer that ({type(error).__name__}: {error})."
        yield history, sources or ""


def add_user_message(message, history):
    """Moves the question into the chat and locks the box until the answer is done (unlock_input).
    Without the lock, Enter is ignored while an answer streams and the next question gets glued to the old text."""
    if not message.strip():
        return gr.update(value=message), history
    return gr.update(value="", interactive=False, placeholder=ANSWERING_PLACEHOLDER), history + [{"role": "user", "content": message}]


def unlock_input():
    return gr.update(interactive=True, placeholder=INPUT_PLACEHOLDER)


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
                    message = gr.Textbox(placeholder=INPUT_PLACEHOLDER, show_label=False)
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
        # always unlock the box afterwards, even if answering failed
        message.submit(add_user_message, [message, chatbot], [message, chatbot]).then(
            chat, chatbot, [chatbot, sources]
        ).then(unlock_input, None, message)
        upload_button.click(upload_files, files, [status, files, *refresh_outputs])
        delete_button.click(
            delete_document,
            to_delete,
            [status, *refresh_outputs],
            js="(doc) => (doc && confirm('Delete \"' + doc + '\" from the index?')) ? doc : null",
        )
        ui.load(refresh_documents, None, refresh_outputs)

    print("Loading search models...")
    pipeline.warm_up(CLIENT_ID)
    ui.launch(inbrowser=True, max_file_size=MAX_FILE_SIZE)


if __name__ == "__main__":
    main()
