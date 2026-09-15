import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class AskRequest(BaseModel):
    question: str
