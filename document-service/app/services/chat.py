from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage
from app.models.document import Document
from app.services import ollama_client
from app.services.extraction import extract_text
from app.services.summarization import MAX_WORDS

SYSTEM_PROMPT_TEMPLATE = (
    "You are a study assistant answering questions about a specific document. "
    "Base your answers only on the document text below; if the answer isn't "
    "in the document, say so instead of guessing.\n\n---\n{document_text}\n---"
)


def _build_system_message(document: Document) -> dict:
    text = extract_text(document)
    words = text.split()
    if len(words) > MAX_WORDS:
        text = " ".join(words[:MAX_WORDS])
    return {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(document_text=text)}


def ask_question(db: Session, document: Document, question: str) -> ChatMessage:
    """Loads the document's prior conversation, sends the full turn history
    (plus the document's own text as a system message) to Ollama, and
    persists both the new user question and the assistant's reply. Unlike
    summarization, a failure here propagates uncaught — this is a
    synchronous, user-initiated call, so the caller should see it failed
    rather than silently get nothing back."""
    prior_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.document_id == document.id)
        .order_by(ChatMessage.created_at)
        .all()
    )

    user_message = ChatMessage(document_id=document.id, role="user", content=question)
    db.add(user_message)
    db.commit()

    ollama_messages = [_build_system_message(document)]
    ollama_messages.extend({"role": m.role, "content": m.content} for m in prior_messages)
    ollama_messages.append({"role": "user", "content": question})

    reply_text = ollama_client.chat(ollama_messages)

    assistant_message = ChatMessage(document_id=document.id, role="assistant", content=reply_text)
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return assistant_message
