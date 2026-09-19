"""
What the rest of the app is allowed to know about storage.

Every method speaks in the domain models from `app/common/models`, so no ORM row
and no SQLAlchemy type crosses this boundary, and no method takes a session —
where the rows live is the implementation's business.

Methods come in two kinds, and each one says which it is:

*Flushing* — the ordinary kind. The write is visible to the rest of the scope
and the scope that opened the connection decides when it becomes durable. For
SQL that scope is the request.

*Durable on return* — the write is committed before the method returns. Reserved
for effects that must hold regardless of what the caller does next: spending a
question, spending a single-use claim link, claiming the right to send one
notification. If those were merely flushed, a request that failed afterwards
would hand the question back — and a client that aborts a stream would ask for
free. Every backend can honour this: SQL commits, a document store does an
atomic find-and-modify, a file store fsyncs.

The distinction is in the name and the docstring rather than a flag, because no
caller can usefully branch on it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from app.common.logging import logging
from app.common.models import (
    ChatMessage,
    Conversation,
    ConversationPreview,
    Grant,
    RefreshSession,
    User,
)

logger = logging.logger


@dataclass(frozen=True, slots=True)
class ReplyOutcome:
    """
    How a turn ended, as one value rather than seven trailing parameters.

    Everything here is observed after the model has answered — or failed to —
    and none of it changes what is stored, only what is recorded about it.
    """

    status: str  # "completed" | "aborted" | "failed"
    finish_reason: str | None = None
    tool_names: list[str] = field(default_factory=list)
    tool_calls_count: int = 0
    model: str | None = None
    latency_ms: int | None = None
    error: str | None = None


class RepositoryBase(ABC):
    """Shared plumbing. A repository is what it can do, not what it inherits."""

    def __init__(self) -> None:
        self.logger = logger


class UserRepository(RepositoryBase):
    """
    What the rest of the app is allowed to know about storing users.

    Two things make this a seam rather than a spelling of `db.execute`. Every
    method speaks in `User`, the domain model, so no `DatabaseUser` and no
    SQLAlchemy type crosses it — a caller can be exercised against an in-memory
    implementation with no database in the process at all. And no method takes a
    session: where the rows live, and who holds the transaction open, is the
    concrete repository's business.

    Both methods here are the flushing kind: the scope that opened the
    connection decides when a user becomes durable, so nothing about storing
    one has to be named by a caller.
    """

    @abstractmethod
    async def get_by_name(self, name: str) -> User | None:
        """The user with this name, or None. Names are unique."""

    @abstractmethod
    async def add(self, name: str, email: str | None, phone: str | None) -> User:
        """Store a new user and return it, with its assigned id populated."""


class TokenRepository(RepositoryBase):
    """
    What the rest of the app is allowed to know about storing grants.

    `get` returns a grant without judging it. Whether an expired or exhausted
    one is an error is the caller's business — `/session` deliberately reports
    a spent quota as zero rather than raising — so the validity rules live in
    the auth service, not here.

    `consume_query` is the exception, and has to be: what makes a spend safe is
    that the store arbitrates the race, so only the store can say whether a
    failed spend was a revoked grant, an expired one or an exhausted one. The
    diagnosis is inseparable from the statement, and so are the errors.
    """

    @abstractmethod
    async def add(self, grant: Grant) -> Grant:
        """Store a new grant and return it as stored. Flushes."""

    @abstractmethod
    async def get(self, token_id: uuid.UUID) -> Grant | None:
        """The grant with this id, or None. No validity judgement."""

    @abstractmethod
    async def consume_query(
        self, token_id: uuid.UUID, expected_version: int | None = None
    ) -> Grant:
        """
        Spend one question against this grant, atomically, and return it as it
        now stands. Durable on return: a spend a later failure could undo is a
        free question, and a client that aborts its stream would take them all.

        The version is checked as part of the same condition rather than after
        it, so presenting a v1-shaped token against a v2 grant costs nothing.

        Raises InvalidToken, TokenRevoked, TokenExpired or QuotaExhausted —
        whichever of them explains why the spend did not happen.
        """

    @abstractmethod
    async def claim_once(self, token_id: uuid.UUID) -> bool:
        """
        Spend this grant's claim link. True if this call was the one that spent
        it. Durable on return — the whole mechanism is that a second caller
        cannot also win, which a write a failure could undo would not provide.

        A False is not an error here; what a second presentation means is the
        caller's decision.
        """

    @abstractmethod
    async def mark_owner_notified(self, token_id: uuid.UUID) -> bool:
        """
        Claim the right to send one operator notification for this grant. True
        if this call won it. Durable on return, for the same reason as
        `claim_once`: a dead link hit in a loop must produce one message.
        """

    @abstractmethod
    async def revoke(self, token_id: uuid.UUID) -> bool:
        """
        Revoke the grant itself. True if it was already revoked. Durable on
        return — a kill switch that a later failure could undo is not one.

        Cutting the sessions under it is a separate call on the session
        repository; a grant and its sessions are different aggregates, and
        revoking the grant is the half that matters, since the claim link is
        the durable credential.
        """



class RefreshSessionRepository(RepositoryBase):
    """
    What the rest of the app is allowed to know about storing refresh sessions.

    `rotate` is deliberately one method rather than an insert plus an update the
    caller sequences. The successor has to exist before the predecessor points
    at it, the predecessor is only spendable once, and losing that race has to
    leave nothing behind — three things that are one decision, and one a backend
    has to make with whatever it has. Splitting them would put the race back in
    the caller's hands, where it cannot be won.

    Token hashing is not here. A caller hands over a session that already
    carries its `token_hash`, the same way issuing a grant does.
    """

    @abstractmethod
    async def get(self, session_id: uuid.UUID) -> RefreshSession | None:
        """The session with this id, or None."""

    @abstractmethod
    async def add(self, session: RefreshSession) -> RefreshSession:
        """Open a new session on a grant and return it as stored. Flushes."""

    @abstractmethod
    async def rotate(
        self, session_id: uuid.UUID, successor: RefreshSession
    ) -> RefreshSession:
        """
        Exchange one session's token for its successor, atomically, and return
        the successor. Durable on return: a rotation a later failure could undo
        would hand a spent refresh token back to a client that already has its
        replacement.

        Losing the race means the token was already spent — either a client
        retrying or a stolen token being replayed, and nothing here can tell
        which. Outside the grace window this cuts every session on the grant and
        raises RefreshTokenReplayed; inside it, RotationInProgress, because that
        is a client racing itself and cutting would log the hirer out of their
        own tab.

        Raises InvalidRefreshToken, RefreshTokenExpired, SessionRevoked,
        RotationInProgress or RefreshTokenReplayed.
        """

    @abstractmethod
    async def revoke_all_for_grant(self, token_id: uuid.UUID) -> int:
        """
        Cut every live session on a grant and return how many. Durable on
        return — this is the response to a suspected theft.
        """


class TranscriptRepository(RepositoryBase):
    """
    What the rest of the app is allowed to know about capturing a transcript.

    This one owns its own connection scope rather than borrowing the request's,
    and that is forced rather than stylistic: on client abort the request
    session is already closed by the time the recorder's `finally` block runs,
    so writing through it would be a use-after-close. Owning the scope also
    keeps one code path for the streaming and non-streaming endpoints.

    Both methods are coarse on purpose. Splitting `record_question` into a
    lookup and two writes would put the scope back in the caller's hands, which
    is exactly what cannot work after an abort.

    These may still raise. Capturing a transcript must never change what the
    hirer sees, but that is a policy the chat service applies — it is the thing
    that knows a reply is at stake — not something every backend has to
    remember to implement.
    """

    @abstractmethod
    async def record_question(
        self,
        token_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message: str,
        endpoint: str,
        request_id: str,
    ) -> uuid.UUID:
        """
        Store the question and return the conversation it belongs to, reusing
        the one named if it is genuinely this grant's and starting a new one
        otherwise. Durable on return: this is what guarantees the question
        survives whatever then happens to the stream, the model or the process.
        """

    @abstractmethod
    async def record_reply(
        self,
        token_id: uuid.UUID,
        conversation_id: uuid.UUID,
        reply: str,
        endpoint: str,
        request_id: str,
        outcome: ReplyOutcome,
    ) -> None:
        """
        Store the reply as it finished — completed, aborted or failed.

        Enrichment rather than durability: the question is already stored by the
        time this runs, so a failure here loses the reply, never the question.
        """


class ConversationRepository(RepositoryBase):
    """
    What the rest of the app is allowed to know about reading transcripts back.

    The same two tables as TranscriptRepository, deliberately split from it:
    these run inside a request like every other repository, while the recorders
    have to outlive one. Session ownership is the whole difference, and one
    abstraction claiming both would have to lie about it somewhere.
    """

    @abstractmethod
    async def list_previews(
        self,
        limit: int = 50,
        offset: int = 0,
        company: str | None = None,
        since: datetime | None = None,
    ) -> list[ConversationPreview]:
        """Conversations, newest activity first, each with enough of its
        transcript to be scannable without opening it."""

    @abstractmethod
    async def get_with_messages(
        self, conversation_id: uuid.UUID
    ) -> tuple[Conversation | None, list[ChatMessage]]:
        """The full transcript, oldest first, or (None, []) if there is no such
        conversation."""

    @abstractmethod
    async def exists(self, conversation_id: uuid.UUID) -> bool:
        """Whether this conversation is there — for callers that need to answer
        a 404 and nothing more."""

    @abstractmethod
    async def redact(self, conversation_id: uuid.UUID) -> int:
        """
        Erase the content of every message, keeping the rows, and return how
        many were erased. Durable on return — an erasure a later failure could
        undo is not one.

        Deletion is not offered: every foreign key here is RESTRICT, and the
        operational record — counts, timings, sizes — is worth keeping.
        """
