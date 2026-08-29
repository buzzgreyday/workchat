import uuid
from datetime import datetime
from typing import Any, List, Optional, Literal

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
    skill_notes: dict[str, str] = {}  # optional {tag: "scope/caveat note"}, e.g.
                            # {"kubernetes": "Deployed existing services; did not design cluster architecture."}

class ChatRequest(BaseModel):
    # Bounded so it cannot exceed the chat_messages.content column, and to cap
    # what a single request can cost in OpenAI tokens.
    message: str = Field(min_length=1, max_length=4000)
    # Parameterised so the shape is stated rather than implied: after pydantic
    # has parsed the request body these really are dicts, whatever the client sent.
    history: list[dict[str, Any]] = []  # [{"role": "user"/"assistant"/"tool", ...}]
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
    # 1 mints the ?token= access JWT as before; 2 mints a ?claim= link the hirer
    # exchanges for a refresh/access pair. Defaults to 1 so an existing caller
    # that never heard of versions keeps getting exactly what it got before.
    version: Literal[1, 2] = 1

class ChatResponse(BaseModel):
    type: str | None = None
    reply: str
    history: list[dict[str, Any]]
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
    # Which token flow the caller arrived on. 1 = the long-lived ?token= JWT,
    # 2 = an access token minted from a claim. Carried so handlers and logs can
    # tell the two apart; the chat path deliberately treats them identically.
    version: int = 1
    # v2 only: the refresh-token row the access token was minted from, i.e. which
    # of the hirer's devices this request came from.
    session_id: str | None = None
    # When the grant itself lapses — not the access token, which is far shorter
    # lived and reissued on demand. This is the date after which no amount of
    # refreshing helps, which is the one a client can usefully display.
    expires_at: datetime

class JWT(BaseModel):
    """
    Every token this service mints, v1 and v2 alike.

    v1 tokens carry no `ver`, and that absence is the version signal — the tokens
    already handed out cannot be reissued, so the decoder has to read an unmarked
    token as version 1 forever. `generate` drops None fields for the same reason:
    a v1 token minted today must be claim-for-claim what one minted last month
    was, not the same thing plus a row of nulls.
    """
    sub: str # Freetext: currently used as identifier by the chatbot
    iat: int
    exp: int
    # default_factory so each instance gets its own jti; using
    # `str(uuid.uuid4())` as a bare default fires once at class-definition
    # time and every JWT() would share that same id.
    jti: str = Field(default_factory=lambda: str(uuid.uuid4()))
    max_queries: int | None = 20
    # --- v2 claims (all None on a v1 token) ---
    ver: int | None = None
    typ: Literal["claim", "refresh", "access"] | None = None
    # The grant. In v1 `jti` served as both the token id and the grant id; v2
    # separates them, because a grant now mints many tokens and each needs its
    # own id while still consuming the one shared quota.
    tid: str | None = None
    # The refresh-token row this access token came from. Only set on typ="access".
    sid: str | None = None

    def generate(self, secret_key: str, algorithm: str) -> str:
        return jwt.encode(self.model_dump(exclude_none=True), secret_key, algorithm=algorithm)


class TokenPair(BaseModel):
    """
    Internal result of a claim or a rotation. Not a response model: the refresh
    token leaves the process in a Set-Cookie header, never in a body, so that
    script running on the page cannot read it.
    """
    access_token: str
    refresh_token: str
    # Seconds until access_token expires, so a client can schedule a refresh
    # instead of waiting to be told 401. Clamped to the grant's own expiry.
    expires_in: int
    refresh_expires_in: int


class SessionOut(BaseModel):
    """What /v2/auth/claim and /v2/auth/refresh actually return. Deliberately
    missing the refresh token — see TokenPair."""
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    refresh_expires_in: int


class SessionInfo(BaseModel):
    """
    What GET /session reports: who the session belongs to and what is left of it.

    Exists so the quota is knowable *before* the first question rather than only
    as a side effect of asking one. Reading it spends nothing.
    """
    subject: str
    version: int
    usage: Usage
    expires_at: datetime
    session_id: str | None = None


class ClaimRequest(BaseModel):
    claim_token: str = Field(min_length=1, max_length=4096)


class RefreshRequest(BaseModel):
    # Optional because the cookie is the normal carrier. A non-browser client
    # (curl, a test, a future mobile app) can still put it in the body.
    refresh_token: str | None = Field(default=None, min_length=1, max_length=4096)

