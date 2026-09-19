"""
The repositories, both as they are implemented and as they are depended upon.

The fakes at the bottom are the point of the abstraction: two dicts implement
the whole of it, so the caller that types against the base classes runs with no
database in the process.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.common.models import Grant, User
from app.repositories.base import TokenRepositoryBase, UserRepositoryBase
from app.repositories.sql import SQLTokenRepository, SQLUserRepository


@pytest.fixture
def users(db_session):
    return SQLUserRepository(db=db_session)


@pytest.fixture
def tokens(db_session):
    return SQLTokenRepository(db=db_session)


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
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[Grant] = []

    async def add(self, grant: Grant) -> Grant:
        self.rows.append(grant)
        return grant


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
