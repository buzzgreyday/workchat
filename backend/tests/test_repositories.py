"""
The repositories, both as they are implemented and as they are depended upon.

The fakes at the bottom are the point of the abstraction: two dicts implement
the whole of it, so the caller that types against the base classes runs with no
database in the process.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.common.schemas import DatabaseChatMessage, DatabaseRefreshToken

from app.common.exceptions import (
    InvalidRefreshToken,
    InvalidToken,
    QuotaExhausted,
    RefreshTokenReplayed,
    RotationInProgress,
    TokenExpired,
    TokenRevoked,
)
from app.common.models import Grant, RefreshSession, User
from app.repositories.base import (
    ReplyOutcome,
    SessionRepositoryBase,
    TokenRepositoryBase,
    UserRepositoryBase,
)
from app.repositories.sql import (
    SQLConversationRepository,
    SQLSessionRepository,
    SQLTokenRepository,
    SQLTranscriptRepository,
    SQLUserRepository,
)


@pytest.fixture
def users(db_session):
    return SQLUserRepository(db=db_session)


@pytest.fixture
def tokens(db_session):
    return SQLTokenRepository(db=db_session)


@pytest.fixture
def sessions(db_session):
    return SQLSessionRepository(db=db_session)


@pytest.fixture
async def grant(users, tokens):
    """A stored grant with a user behind it, for the FK."""
    user = await users.add(name="Acme", email=None, phone=None)
    return await tokens.add(make_grant(user.id))


def make_session(token_id: uuid.UUID, **overrides) -> RefreshSession:
    defaults = dict(
        token_id=token_id,
        token_hash=uuid.uuid4().hex,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=7),
    )
    return RefreshSession(**{**defaults, **overrides})


def make_grant(user_id: uuid.UUID, **overrides) -> Grant:
    defaults = dict(
        user_id=user_id,
        subject="Ada",
        token_hash=uuid.uuid4().hex,
        max_queries=5,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=1),
        created_at=datetime.now(tz=timezone.utc),
    )
    return Grant(**{**defaults, **overrides})


# --- users ---------------------------------------------------------------


async def test_get_by_name_missing_returns_none(users):
    assert await users.get_by_name("nobody") is None


async def test_add_returns_domain_user_with_id(users):
    user = await users.add(name="Acme", email="ada@example.com", phone="555")

    assert isinstance(user, User)
    assert isinstance(user.id, uuid.UUID)
    assert user.name == "Acme"


async def test_add_then_get_by_name_round_trips(users):
    added = await users.add(name="Acme", email=None, phone=None)
    found = await users.get_by_name("Acme")

    assert found is not None
    assert found.id == added.id


async def test_email_is_lowercased_on_write(users):
    await users.add(name="Acme", email="Ada@Example.COM", phone=None)
    found = await users.get_by_name("Acme")

    assert found is not None
    assert found.email == "ada@example.com"


# --- tokens --------------------------------------------------------------


async def test_token_add_returns_domain_grant(users, tokens):
    user = await users.add(name="Acme", email=None, phone=None)
    grant = await tokens.add(make_grant(user.id, subject="Ada"))

    assert isinstance(grant, Grant)
    assert grant.user_id == user.id
    assert grant.subject == "Ada"
    # Column defaults the domain model should reflect, not invent.
    assert grant.used_queries == 0
    assert grant.revoked_at is None
    assert grant.claimed_at is None


async def test_token_add_keeps_the_id_it_was_given(users, tokens):
    """The JWT's jti is minted before the row, and has to match it."""
    user = await users.add(name="Acme", email=None, phone=None)
    token_id = uuid.uuid4()

    grant = await tokens.add(make_grant(user.id, id=token_id))

    assert grant.id == token_id


# --- spending a grant ----------------------------------------------------


async def test_consume_query_spends_one(tokens, grant):
    spent = await tokens.consume_query(grant.id)

    assert spent.used_queries == 1
    assert spent.max_queries == grant.max_queries


async def test_consume_query_is_durable_on_return(tokens, grant, db_session):
    """
    The contract that makes the spend safe. If this were merely flushed, a
    request failing afterwards would hand the question back — and a client that
    aborts its stream would ask for free.
    """
    await tokens.consume_query(grant.id)
    await db_session.rollback()

    still = await tokens.get(grant.id)
    assert still is not None
    assert still.used_queries == 1


async def test_consume_query_raises_when_the_quota_is_gone(tokens, grant):
    for _ in range(grant.max_queries):
        await tokens.consume_query(grant.id)

    with pytest.raises(QuotaExhausted):
        await tokens.consume_query(grant.id)


async def test_consume_query_raises_on_a_revoked_grant(tokens, grant):
    await tokens.revoke(grant.id)

    with pytest.raises(TokenRevoked):
        await tokens.consume_query(grant.id)


async def test_consume_query_raises_on_an_expired_grant(users, tokens):
    user = await users.add(name="Stale", email=None, phone=None)
    expired = await tokens.add(
        make_grant(user.id, expires_at=datetime.now(tz=timezone.utc) - timedelta(days=1))
    )

    with pytest.raises(TokenExpired):
        await tokens.consume_query(expired.id)


async def test_consume_query_rejects_a_version_mismatch_without_spending(tokens, grant):
    """A v1-shaped token against a v2 grant must not cost one of its questions."""
    with pytest.raises(InvalidToken):
        await tokens.consume_query(grant.id, expected_version=2)

    unspent = await tokens.get(grant.id)
    assert unspent is not None
    assert unspent.used_queries == 0


async def test_consume_query_raises_for_an_unknown_grant(tokens):
    with pytest.raises(InvalidToken):
        await tokens.consume_query(uuid.uuid4())


async def test_claim_once_wins_exactly_once(tokens, grant):
    assert await tokens.claim_once(grant.id) is True
    assert await tokens.claim_once(grant.id) is False


async def test_revoke_reports_whether_it_was_already_revoked(tokens, grant):
    assert await tokens.revoke(grant.id) is False
    assert await tokens.revoke(grant.id) is True


async def test_mark_owner_notified_throttles(tokens, grant):
    assert await tokens.mark_owner_notified(grant.id) is True
    assert await tokens.mark_owner_notified(grant.id) is False


# --- refresh sessions ----------------------------------------------------


async def test_session_add_and_get_round_trip(sessions, grant):
    added = await sessions.add(make_session(grant.id))
    found = await sessions.get(added.id)

    assert found is not None
    assert found.id == added.id
    assert found.token_id == grant.id


async def test_rotate_chains_predecessor_to_successor(sessions, grant):
    original = await sessions.add(make_session(grant.id))
    successor = await sessions.rotate(original.id, make_session(grant.id))

    spent = await sessions.get(original.id)
    assert spent is not None
    assert spent.revoked_at is not None
    assert spent.rotated_to == successor.id
    assert spent.last_used_at is not None


async def test_rotate_inside_the_grace_window_does_not_cut(sessions, grant):
    """A client racing itself keeps its session; cutting would log it out."""
    original = await sessions.add(make_session(grant.id))
    await sessions.rotate(original.id, make_session(grant.id))

    with pytest.raises(RotationInProgress):
        await sessions.rotate(original.id, make_session(grant.id))


async def test_replay_after_the_grace_window_cuts_every_session(
    sessions, grant, db_session
):
    """
    The branch that matters most: a refresh token presented long after it was
    spent is indistinguishable from a stolen one, so the whole grant is cut and
    the hirer re-claims.
    """
    original = await sessions.add(make_session(grant.id))
    successor = await sessions.rotate(original.id, make_session(grant.id))

    # Age the rotation past the grace window, the way test_auth.py does.
    await db_session.execute(
        update(DatabaseRefreshToken)
        .where(DatabaseRefreshToken.id == original.id)
        .values(revoked_at=datetime.now(tz=timezone.utc) - timedelta(minutes=10))
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()

    with pytest.raises(RefreshTokenReplayed) as caught:
        await sessions.rotate(original.id, make_session(grant.id))

    assert caught.value.token_id == grant.id
    cut = await sessions.get(successor.id)
    assert cut is not None
    assert cut.revoked_at is not None, "the live successor must be cut too"


async def test_rotate_raises_for_an_unknown_session(sessions, grant):
    with pytest.raises(InvalidRefreshToken):
        await sessions.rotate(uuid.uuid4(), make_session(grant.id))


async def test_revoke_all_for_grant_cuts_live_sessions_only(sessions, grant):
    await sessions.add(make_session(grant.id))
    await sessions.add(make_session(grant.id))

    assert await sessions.revoke_all_for_grant(grant.id) == 2
    assert await sessions.revoke_all_for_grant(grant.id) == 0


# --- durability ---------------------------------------------------------


async def test_repositories_only_flush(users, db_session):
    """
    A repository never commits. What it writes is visible within the session and
    gone if that session's transaction is discarded — which is what lets the
    request scope, not the service, decide when a write becomes durable.
    """
    await users.add(name="Acme", email=None, phone=None)
    assert await users.get_by_name("Acme") is not None

    await db_session.rollback()
    assert await users.get_by_name("Acme") is None


async def test_both_repositories_share_one_transaction(users, tokens, db_session):
    """
    The providers hand both repositories the same session, so a user and the
    grant pointing at it rise and fall together without either naming a
    transaction.
    """
    user = await users.add(name="Acme", email=None, phone=None)
    await tokens.add(make_grant(user.id))

    await db_session.rollback()
    assert await users.get_by_name("Acme") is None


# --- the seam ------------------------------------------------------------


class FakeUserRepository(UserRepositoryBase):
    """A complete user repository with no database behind it."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: dict[str, User] = {}

    async def get_by_name(self, name: str) -> User | None:
        return self.rows.get(name)

    async def add(self, name: str, email: str | None, phone: str | None) -> User:
        user = User(name=name, email=email, phone=phone)
        self.rows[name] = user
        return user


class FakeTokenRepository(TokenRepositoryBase):
    """A complete grant repository with no database behind it."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[Grant] = []

    def _find(self, token_id: uuid.UUID) -> Grant | None:
        return next((g for g in self.rows if g.id == token_id), None)

    async def add(self, grant: Grant) -> Grant:
        self.rows.append(grant)
        return grant

    async def get(self, token_id: uuid.UUID) -> Grant | None:
        return self._find(token_id)

    async def consume_query(
        self, token_id: uuid.UUID, expected_version: int | None = None
    ) -> Grant:
        grant = self._find(token_id)
        if grant is None:
            raise InvalidToken()
        if grant.revoked_at is not None:
            raise TokenRevoked()
        if expected_version is not None and grant.version != expected_version:
            raise InvalidToken()
        if grant.expires_at <= datetime.now(tz=timezone.utc):
            raise TokenExpired()
        if grant.used_queries >= grant.max_queries:
            raise QuotaExhausted()
        spent = grant.model_copy(update={"used_queries": grant.used_queries + 1})
        self.rows[self.rows.index(grant)] = spent
        return spent

    async def claim_once(self, token_id: uuid.UUID) -> bool:
        grant = self._find(token_id)
        if grant is None or grant.claimed_at is not None:
            return False
        self.rows[self.rows.index(grant)] = grant.model_copy(
            update={"claimed_at": datetime.now(tz=timezone.utc)}
        )
        return True

    async def mark_owner_notified(self, token_id: uuid.UUID) -> bool:
        grant = self._find(token_id)
        if grant is None or grant.owner_notified_at is not None:
            return False
        self.rows[self.rows.index(grant)] = grant.model_copy(
            update={"owner_notified_at": datetime.now(tz=timezone.utc)}
        )
        return True

    async def revoke(self, token_id: uuid.UUID) -> bool:
        grant = self._find(token_id)
        if grant is None or grant.revoked_at is not None:
            return True
        self.rows[self.rows.index(grant)] = grant.model_copy(
            update={"revoked_at": datetime.now(tz=timezone.utc)}
        )
        return False


class FakeSessionRepository(SessionRepositoryBase):
    """Enough of a session repository to run the auth service without a database."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: dict[uuid.UUID, RefreshSession] = {}

    async def get(self, session_id: uuid.UUID) -> RefreshSession | None:
        return self.rows.get(session_id)

    async def add(self, session: RefreshSession) -> RefreshSession:
        self.rows[session.id] = session
        return session

    async def rotate(
        self, session_id: uuid.UUID, successor: RefreshSession
    ) -> RefreshSession:
        existing = self.rows.get(session_id)
        if existing is None:
            raise InvalidRefreshToken()
        if existing.revoked_at is not None:
            raise RefreshTokenReplayed(existing.token_id)
        now = datetime.now(tz=timezone.utc)
        self.rows[session_id] = existing.model_copy(
            update={"revoked_at": now, "last_used_at": now, "rotated_to": successor.id}
        )
        self.rows[successor.id] = successor
        return successor

    async def revoke_all_for_grant(self, token_id: uuid.UUID) -> int:
        cut = 0
        for key, row in self.rows.items():
            if row.token_id == token_id and row.revoked_at is None:
                self.rows[key] = row.model_copy(
                    update={"revoked_at": datetime.now(tz=timezone.utc)}
                )
                cut += 1
        return cut


async def test_fake_repository_satisfies_the_abstraction():
    fake = FakeUserRepository()

    assert await fake.get_by_name("Acme") is None
    added = await fake.add(name="Acme", email=None, phone=None)

    found = await fake.get_by_name("Acme")
    assert found is not None
    assert found.id == added.id


async def test_issue_token_runs_without_a_database():
    """
    The whole point of the seam: the service never names a backend, so it runs
    against in-memory repositories with no engine, no session, no SQLAlchemy.
    """
    from app.common.models import IssueTokenRequest
    from app.services.admin import issue_token

    users = FakeUserRepository()
    tokens = FakeTokenRepository()

    raw = await issue_token(
        IssueTokenRequest(subject="Ada", company="Acme", max_queries=3),
        users=users,
        tokens=tokens,
    )

    assert raw.count(".") == 2  # a JWT
    assert len(tokens.rows) == 1
    assert tokens.rows[0].user_id == users.rows["Acme"].id


async def test_issue_token_reuses_an_existing_user():
    """
    Re-issuing for a company already stored must attach the new grant to the
    same user. The branch that decides this lives in the service now, so this is
    where it is tested — and it needs no database to say so.
    """
    from app.common.models import IssueTokenRequest
    from app.services.admin import issue_token

    users = FakeUserRepository()
    tokens = FakeTokenRepository()
    req = IssueTokenRequest(subject="Ada", company="Acme", max_queries=3)

    await issue_token(req, users=users, tokens=tokens)
    await issue_token(req, users=users, tokens=tokens)

    assert len(users.rows) == 1, "the second issue must not create a second user"
    assert len(tokens.rows) == 2
    assert tokens.rows[0].user_id == tokens.rows[1].user_id


# --- transcripts ---------------------------------------------------------


@pytest.fixture
def transcripts(session_maker):
    return SQLTranscriptRepository(session_maker)


@pytest.fixture
def conversations(db_session):
    return SQLConversationRepository(db=db_session)


async def test_record_question_starts_a_conversation(transcripts, grant):
    conversation_id = await transcripts.record_question(
        token_id=grant.id,
        conversation_id=None,
        message="what did you build",
        endpoint="/chat",
        request_id=uuid.uuid4().hex,
    )

    assert isinstance(conversation_id, uuid.UUID)


async def test_record_question_reuses_its_own_conversation(transcripts, grant):
    first = await transcripts.record_question(
        token_id=grant.id, conversation_id=None, message="one",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )
    second = await transcripts.record_question(
        token_id=grant.id, conversation_id=first, message="two",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )

    assert second == first


async def test_a_conversation_belonging_to_another_grant_is_not_reused(
    transcripts, users, tokens, grant
):
    """
    The security boundary. Without the token_id predicate any bearer could
    append into another hirer's conversation by guessing an id.
    """
    other_user = await users.add(name="Other", email=None, phone=None)
    other_grant = await tokens.add(make_grant(other_user.id))

    theirs = await transcripts.record_question(
        token_id=other_grant.id, conversation_id=None, message="theirs",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )
    mine = await transcripts.record_question(
        token_id=grant.id, conversation_id=theirs, message="mine",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )

    assert mine != theirs, "a guessed id must start a new conversation, not join one"


async def test_concurrent_questions_both_count(transcripts, conversations, grant):
    """
    The lost update. Both turns land on one conversation at once; a Python-side
    `message_count += 1` reads the same stale value twice and drops one.
    """
    conversation_id = await transcripts.record_question(
        token_id=grant.id, conversation_id=None, message="first",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )

    await asyncio.gather(
        *[
            transcripts.record_question(
                token_id=grant.id, conversation_id=conversation_id, message=f"q{i}",
                endpoint="/chat", request_id=uuid.uuid4().hex,
            )
            for i in range(4)
        ]
    )

    conversation, messages = await conversations.get_with_messages(conversation_id)
    assert conversation is not None
    assert len(messages) == 5, "every question must be stored"
    assert conversation.message_count == 5, "and every one of them counted"


async def test_record_reply_stores_the_outcome(transcripts, conversations, grant):
    conversation_id = await transcripts.record_question(
        token_id=grant.id, conversation_id=None, message="ask",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )
    await transcripts.record_reply(
        token_id=grant.id,
        conversation_id=conversation_id,
        reply="answered",
        endpoint="/chat",
        request_id=uuid.uuid4().hex,
        outcome=ReplyOutcome(
            status="completed", finish_reason="stop", tool_names=["search_cv"],
            tool_calls_count=1, model="gpt-4.1-nano", latency_ms=42,
        ),
    )

    _, messages = await conversations.get_with_messages(conversation_id)
    reply = next(m for m in messages if m.role == "assistant")
    assert reply.status == "completed"
    assert reply.tool_names == "search_cv"
    assert reply.latency_ms == 42


# --- reading conversations back ------------------------------------------


async def test_list_previews_shows_question_and_latest_reply(
    transcripts, conversations, db_session, grant
):
    """
    The first question but the *last* reply — the point of reading these is
    catching a wrong answer, which is wherever the thread ended up.

    The older reply is backdated rather than written a second apart: created_at
    is a server default, and SQLite's CURRENT_TIMESTAMP only has second
    granularity, so two replies written in one second would tie. Postgres gives
    each its own transaction timestamp, so this is a test-harness concern only.
    """
    conversation_id = await transcripts.record_question(
        token_id=grant.id, conversation_id=None, message="the opening question",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )
    for reply in ("first reply", "latest reply"):
        await transcripts.record_reply(
            token_id=grant.id, conversation_id=conversation_id, reply=reply,
            endpoint="/chat", request_id=uuid.uuid4().hex,
            outcome=ReplyOutcome(status="completed"),
        )
    await db_session.execute(
        update(DatabaseChatMessage)
        .where(DatabaseChatMessage.content == "first reply")
        .values(created_at=datetime.now(tz=timezone.utc) - timedelta(hours=1))
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()

    previews = await conversations.list_previews()

    assert len(previews) == 1
    assert previews[0].preview == "the opening question"
    assert previews[0].reply_preview == "latest reply", "the last reply, not the first"


async def test_list_previews_truncates(transcripts, conversations, grant):
    conversation_id = await transcripts.record_question(
        token_id=grant.id, conversation_id=None, message="q" * 500,
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )
    await transcripts.record_reply(
        token_id=grant.id, conversation_id=conversation_id, reply="r" * 500,
        endpoint="/chat", request_id=uuid.uuid4().hex,
        outcome=ReplyOutcome(status="completed"),
    )

    previews = await conversations.list_previews()

    assert len(previews[0].preview) == 120
    assert len(previews[0].reply_preview) == 200


async def test_list_previews_handles_a_conversation_with_no_reply(
    transcripts, conversations, grant
):
    await transcripts.record_question(
        token_id=grant.id, conversation_id=None, message="unanswered",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )

    previews = await conversations.list_previews()

    assert previews[0].preview == "unanswered"
    assert previews[0].reply_preview is None


async def test_list_previews_filters_by_company(transcripts, conversations, users, tokens, grant):
    other_user = await users.add(name="Other", email=None, phone=None)
    other_grant = await tokens.add(make_grant(other_user.id, company="Other"))
    await transcripts.record_question(
        token_id=grant.id, conversation_id=None, message="acme",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )
    await transcripts.record_question(
        token_id=other_grant.id, conversation_id=None, message="other",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )

    assert len(await conversations.list_previews()) == 2
    assert len(await conversations.list_previews(company="Other")) == 1


async def test_exists(conversations, transcripts, grant):
    conversation_id = await transcripts.record_question(
        token_id=grant.id, conversation_id=None, message="hi",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )

    assert await conversations.exists(conversation_id) is True
    assert await conversations.exists(uuid.uuid4()) is False


async def test_redact_nulls_content_but_keeps_rows(transcripts, conversations, grant):
    conversation_id = await transcripts.record_question(
        token_id=grant.id, conversation_id=None, message="sensitive",
        endpoint="/chat", request_id=uuid.uuid4().hex,
    )

    assert await conversations.redact(conversation_id) == 1

    conversation, messages = await conversations.get_with_messages(conversation_id)
    assert conversation is not None
    assert conversation.redacted_at is not None
    assert len(messages) == 1, "the row survives"
    assert messages[0].content is None
    assert messages[0].content_chars == len("sensitive"), "the size signal survives"
