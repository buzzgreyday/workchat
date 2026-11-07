import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.common.models.utc import UTCDateTime

MessageRole = Literal["user", "assistant"]
# How a reply ended: the recorder writes one of these whatever happened.
ReplyStatus = Literal["completed", "aborted", "failed"]
# A question is stored as "received" before the model is called.
MessageStatus = Literal["received", ReplyStatus]


class ChatMessage(BaseModel):
    """
    One side of a turn — the question as received, or the reply as it finished.

    `content` is nullable because retention scrubs it in place, and because a
    turn can end with no text at all. `content_chars` is the pre-truncation
    length, so the size signal survives the text being gone.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    conversation_id: uuid.UUID
    token_id: uuid.UUID
    request_id: str
    role: MessageRole
    content: str | None = None
    content_chars: int | None = None
    truncated: int = 0
    endpoint: str
    status: MessageStatus
    finish_reason: str | None = None
    tool_calls_count: int = 0
    tool_names: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    error: str | None = None
    redacted_at: UTCDateTime | None = None
    created_at: UTCDateTime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class Conversation(BaseModel):
    """
    One chat session.

    `subject`, `company` and `job_title` are snapshots of the grant taken at the
    first message rather than references to it — a snapshot still reads
    correctly after the grant behind it is rotated or revoked, which is why
    nothing here traverses back to a token.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    token_id: uuid.UUID
    user_id: uuid.UUID
    subject: str
    company: str | None = None
    job_title: str | None = None
    message_count: int = 0
    last_message_at: UTCDateTime | None = None
    redacted_at: UTCDateTime | None = None
    created_at: UTCDateTime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class ConversationPreview(Conversation):
    """
    A conversation as it appears in a list, with enough of the transcript to be
    scannable without opening it.

    The reply matters as much as the question: the point of reading these is
    catching the agent answering wrongly, which the question alone cannot show.
    Latest reply rather than first, so a thread shows where it ended up.
    """

    preview: str | None = None
    reply_preview: str | None = None