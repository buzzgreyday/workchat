import uuid
from datetime import datetime
from typing import List, Optional, Literal

import jwt
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class Usage(BaseModel):
    used: int
    remaining: int
    max: int

class Record(BaseModel):
    file: str          # relative path, e.g. "experience/company-a.md"
    type: str          # "experience" | "project" | "skill"
    title: str         # e.g. "Senior Engineer @ Acme Corp"
    tags: List[str] = []
    dates: Optional[str] = None
    summary: Optional[str] = None  # 1-liner shown in search results before full fetch
    skill_notes: dict = {}  # optional {tag: "scope/caveat note"}, e.g.
                            # {"kubernetes": "Deployed existing services; did not design cluster architecture."}

class ChatRequest(BaseModel):
    # Bounded so it cannot exceed the chat_messages.content column, and to cap
    # what a single request can cost in OpenAI tokens.
    message: str = Field(min_length=1, max_length=4000)
    history: list = []  # [{"role": "user"/"assistant"/"tool", ...}]
    # Echoed back by the server so a client can keep appending to one thread.
    # Unverifiable client input: the server checks it belongs to the bearer's
    # token and silently starts a new conversation if it doesn't.
    conversation_id: uuid.UUID | None = None

class IssueTokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    # 60s minimum (anything shorter is basically useless) up to 90 days.
    expires_in_seconds: int = Field(default=60 * 60 * 24 * 7, ge=60, le=60 * 60 * 24 * 90)
    max_queries: int = Field(default=20, ge=1, le=1000)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    job_title: str | None = Field(default=None, max_length=255)
    type: Literal["token", "qr"] = "token"

class ChatResponse(BaseModel):
    type: str | None = None
    reply: str
    history: list[dict]
    usage: Usage
    conversation_id: str | None = None


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    request_id: str
    role: str
    content: str | None = None
    content_chars: int | None = None
    truncated: int = 0
    endpoint: str
    status: str
    finish_reason: str | None = None
    tool_calls_count: int = 0
    tool_names: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    error: str | None = None
    redacted_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationSummary(BaseModel):
    id: uuid.UUID
    subject: str
    company: str | None = None
    job_title: str | None = None
    message_count: int
    created_at: datetime
    last_message_at: datetime | None = None
    redacted_at: datetime | None = None
    # The opening question, and how the agent last replied — enough to spot a
    # wrong answer from the list without opening every conversation.
    preview: str | None = None
    reply_preview: str | None = None


class ConversationDetail(BaseModel):
    id: uuid.UUID
    subject: str
    company: str | None = None
    job_title: str | None = None
    message_count: int
    created_at: datetime
    last_message_at: datetime | None = None
    redacted_at: datetime | None = None
    messages: list[ChatMessageOut]

class TokenContext(BaseModel):
    sub: str
    jti: str
    max_queries: int
    used_queries: int
    remaining_queries: int

class JWT(BaseModel):
    sub: str # Freetext: currently used as identifier by the chatbot
    iat: int
    exp: int
    # default_factory so each instance gets its own jti; using
    # `str(uuid.uuid4())` as a bare default fires once at class-definition
    # time and every JWT() would share that same id.
    jti: str = Field(default_factory=lambda: str(uuid.uuid4()))
    max_queries: int = 20

    def generate(self, secret_key: str, algorithm: str) -> str:
        return jwt.encode(self.model_dump(), secret_key, algorithm=algorithm)

