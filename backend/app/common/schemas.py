import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, ForeignKey, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from app.common.db import Base

class DatabaseUser(Base):
    """
    Right now all we need is a unique name, the token will hold the name as "sub"
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DatabaseToken(Base):
    """
    One grant. In v1 the JWT in the ?token= link *was* the grant, so this row and
    that token were the same thing. In v2 the row outlives every token derived
    from it: a claim link, the refresh tokens it mints and the access tokens
    those mint all point back here, and the query quota is still counted here.
    """
    __tablename__ = "tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    subject: Mapped[str] = mapped_column(String(255), index=True)
    company: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    max_queries: Mapped[int] = mapped_column(Integer)
    used_queries: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 1 = the token_hash is a long-lived access token handed out as ?token=.
    # 2 = it is a claim token exchanged at /v2/auth/claim for a refresh/access
    # pair. Defaulted to 1 so every row that predates this column keeps working
    # exactly as it did, which is the whole point of the version claim.
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # When this grant's claim link was first exchanged. The claim stays usable
    # until the grant expires, so this records the first exchange only — it is
    # for spotting a link that was never opened, not for blocking a second one.
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DatabaseRefreshToken(Base):
    """
    One session within a grant.

    A hirer who opens the claim link on their laptop and again on their phone
    gets two rows, each rotating independently, and revoking one leaves the
    other alone. Rotation is why rows are kept rather than updated in place:
    `rotated_to` chains a session's history, so a refresh token presented after
    it was already exchanged is recognisable as a replay rather than merely
    unknown, and the whole chain can be cut.
    """
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tokens.id", ondelete="RESTRICT"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Stamped both when a token is rotated away and when it is cut for replay;
    # `rotated_to` is what tells the two apart.
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rotated_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="RESTRICT"), nullable=True
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DatabaseConversation(Base):
    """
    One conversation per chat session. subject/company/job_title are snapshots of
    the token row at first message: TokenContext drops everything but sub and jti,
    and a snapshot still reads correctly after a token is rotated or revoked.
    """
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tokens.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    subject: Mapped[str] = mapped_column(String(255), index=True)
    company: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    redacted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DatabaseChatMessage(Base):
    """
    One row per side of a turn: the question as received, and the reply as it
    finished (or didn't). Tool arguments and results are deliberately not stored —
    arguments are model-generated derivations of the question, and results are the
    CV markdown already in git.
    """
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"), index=True
    )
    token_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tokens.id", ondelete="RESTRICT"), index=True
    )
    # 32 hex chars: W3C trace-id shaped on purpose. Holds uuid4().hex today; when
    # OpenTelemetry lands it holds the real trace_id, so historical rows join to a
    # trace by plain id lookup with no migration and no backfill.
    request_id: Mapped[str] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(16), index=True)  # "user" | "assistant"
    # Nullable so retention can scrub it in place, and because a turn can end with
    # no text at all. Wider than the String(255) used elsewhere for the obvious
    # reason; ChatRequest.message caps input well below this.
    content: Mapped[str | None] = mapped_column(String(16000), nullable=True)
    content_chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    truncated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    endpoint: Mapped[str] = mapped_column(String(32))
    # "received" (user) | "completed" | "aborted" | "failed" (assistant)
    status: Mapped[str] = mapped_column(String(16), index=True)
    finish_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tool_calls_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tool_names: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    redacted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
