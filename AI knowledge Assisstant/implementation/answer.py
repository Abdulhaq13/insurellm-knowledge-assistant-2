from typing import Iterator

import litellm
from litellm import completion
from langchain_chroma import Chroma
from langchain_core.documents import Document

from implementation.ingest import DB_NAME, embeddings

from dotenv import load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


load_dotenv(override=True)
litellm.suppress_debug_info = True

MODEL = "groq/openai/gpt-oss-120b"

RETRIEVAL_K = 6
HISTORY_TURNS_FOR_RETRIEVAL = 2
MAX_HISTORY_MESSAGES = 6

SYSTEM_PROMPT = """
You are a knowledgeable, friendly assistant representing the company Insurellm.
You are chatting with a user about Insurellm.
If relevant, use the given context to answer any question.
If you don't know the answer, say so.
Context:
{context}
"""

vectorstore = Chroma(persist_directory=DB_NAME, embedding_function=embeddings)
retriever = vectorstore.as_retriever(search_kwargs={"k": RETRIEVAL_K})


@retry(
    retry=retry_if_exception_type((litellm.RateLimitError, litellm.APIConnectionError, litellm.InternalServerError)),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(8),
    reraise=True,
)
def llm(messages: list[dict], **kwargs):
    return completion(model=MODEL, messages=messages, temperature=0, **kwargs)


def fetch_context(question: str) -> list[Document]:
    """
    Retrieve relevant context documents for a question.
    """
    return retriever.invoke(question)


def combined_question(question: str, history: list[dict] = []) -> str:
    """
    Build the retrieval query: the current question first (so embedding truncation
    can only cut older turns), followed by the most recent prior user messages.
    """
    prior = [m["content"] for m in history if m["role"] == "user"][-HISTORY_TURNS_FOR_RETRIEVAL:]
    return "\n".join([question, *reversed(prior)])


def make_messages(question: str, history: list[dict], docs: list[Document]) -> list[dict]:
    context = "\n\n".join(doc.page_content for doc in docs)
    recent = [{"role": m["role"], "content": m["content"]} for m in history[-MAX_HISTORY_MESSAGES:]]
    return (
        [{"role": "system", "content": SYSTEM_PROMPT.format(context=context)}]
        + recent
        + [{"role": "user", "content": question}]
    )


def answer_question(question: str, history: list[dict] = []) -> tuple[str, list[Document]]:
    """
    Answer the given question with RAG; return the answer and the context documents.
    """
    docs = fetch_context(combined_question(question, history))
    response = llm(make_messages(question, history, docs))
    return response.choices[0].message.content, docs


def stream_answer(question: str, history: list[dict] = []) -> Iterator[tuple[str, list[Document]]]:
    """
    Like answer_question, but yields (answer_so_far, docs) as tokens arrive.
    """
    docs = fetch_context(combined_question(question, history))
    answer = ""
    yield answer, docs
    for chunk in llm(make_messages(question, history, docs), stream=True):
        answer += chunk.choices[0].delta.content or ""
        yield answer, docs
