from app.services import ollama_client

# A rough ceiling on how much document text goes into the prompt. Not RAG —
# just a guard against a huge PDF blowing past the model's context window.
# See CLAUDE.md "Planned: AI-assisted learning features" for why there's no
# vector store/chunking here: a single document is expected to fit.
MAX_WORDS = 12000

SYSTEM_PROMPT = (
    "You are a study assistant that writes clear, easy-to-learn-from summaries "
    "of documents. Given the full text of a document, produce a structured "
    "summary: a one-sentence headline, followed by a short list of key points "
    "a learner should take away. Be concise and avoid restating the obvious."
)


def generate_summary(text: str) -> str:
    words = text.split()
    if len(words) > MAX_WORDS:
        text = " ".join(words[:MAX_WORDS])

    return ollama_client.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
    )
