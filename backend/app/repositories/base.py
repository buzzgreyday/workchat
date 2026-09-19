from abc import ABC, abstractmethod

from app.common.logging import logging
from app.common.models import Grant, User

logger = logging.logger


class RepositoryBase(ABC):
    """Shared plumbing. A repository is what it can do, not what it inherits."""

    def __init__(self) -> None:
        self.logger = logger


class UserRepositoryBase(RepositoryBase):
    """
    What the rest of the app is allowed to know about storing users.

    Two things make this a seam rather than a spelling of `db.execute`. Every
    method speaks in `User`, the domain model, so no `DatabaseUser` and no
    SQLAlchemy type crosses it — a caller can be exercised against an in-memory
    implementation with no database in the process at all. And no method takes a
    session: where the rows live, and who holds the transaction open, is the
    concrete repository's business.

    Implementations never commit. The scope that opened the connection owns
    that — for SQL, the request's session — so what durability means is the
    backend's business and no caller has to name it.
    """

    @abstractmethod
    async def get_by_name(self, name: str) -> User | None:
        """The user with this name, or None. Names are unique."""

    @abstractmethod
    async def add(self, name: str, email: str | None, phone: str | None) -> User:
        """Store a new user and return it, with its assigned id populated."""


class TokenRepositoryBase(RepositoryBase):
    """
    What the rest of the app is allowed to know about storing grants.

    Only `add` so far, which is what issuing a link needs. The read and revoke
    paths still live as free functions in `app/services/db.py` because they turn
    on statements a document store has no equivalent of — the quota spend and
    the single-use claim are atomic `UPDATE ... RETURNING`s whose whole value is
    that the database arbitrates the race. Moving those here means deciding what
    they mean for a backend that cannot express them, which is a bigger question
    than this seam needs to answer today.
    """

    @abstractmethod
    async def add(self, grant: Grant) -> Grant:
        """Store a new grant and return it as stored."""

