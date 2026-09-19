"""The refresh_tokens table — one row per session within a grant."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.config import REFRESH_ROTATION_GRACE_SECONDS
from app.common.exceptions import (
    InvalidRefreshToken,
    RefreshTokenExpired,
    RefreshTokenReplayed,
    RotationInProgress,
    SessionRevoked,
)
from app.common.models import RefreshSession
from app.common.models.utc import as_utc
from app.common.schemas import DatabaseRefreshToken
from app.repositories.base import RefreshSessionRepository
from app.repositories.sql._shared import _rowcount


class SQLRefreshSessionRepository(RefreshSessionRepository):
    """The refresh_tokens table, behind RefreshSessionRepository."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    async def get(self, session_id: uuid.UUID) -> RefreshSession | None:
        row = await self.db.get(DatabaseRefreshToken, session_id)
        return RefreshSession.model_validate(row) if row is not None else None

    async def add(self, session: RefreshSession) -> RefreshSession:
        row = self._row(session)
        self.db.add(row)
        await self.db.flush()
        self.logger.info(
            "Opened refresh session",
            extra={"refresh_id": row.id, "token_id": row.token_id},
        )
        return RefreshSession.model_validate(row)

    @staticmethod
    def _row(session: RefreshSession) -> DatabaseRefreshToken:
        return DatabaseRefreshToken(
            id=session.id,
            token_id=session.token_id,
            token_hash=session.token_hash,
            expires_at=session.expires_at,
        )

    async def rotate(
        self, session_id: uuid.UUID, successor: RefreshSession
    ) -> RefreshSession:
        now = datetime.now(timezone.utc)

        existing = await self.db.get(DatabaseRefreshToken, session_id)
        if existing is None:
            self.logger.warning("Unknown refresh token", extra={"refresh_id": session_id})
            raise InvalidRefreshToken()

        # The successor is inserted *before* the predecessor is claimed so that
        # rotated_to has something to point at — the FK is checked immediately,
        # not deferred. If the claiming UPDATE then matches nothing, the
        # rollback takes this insert with it and a lost race leaves no orphan.
        row = self._row(successor)
        self.db.add(row)
        await self.db.flush()

        result = await self.db.execute(
            update(DatabaseRefreshToken)
            .where(
                DatabaseRefreshToken.id == session_id,
                DatabaseRefreshToken.revoked_at.is_(None),
                DatabaseRefreshToken.expires_at > now,
            )
            .values(revoked_at=now, last_used_at=now, rotated_to=successor.id)
            .execution_options(synchronize_session=False)
        )

        if not _rowcount(result):
            await self.db.rollback()
            raise await self._explain_failed_rotation(session_id, now)

        # Durable before returning: the client is handed this successor, so a
        # rotation the rest of the request could undo would leave it holding a
        # token the store has never seen.
        await self.db.commit()
        rotated = RefreshSession.model_validate(row)
        self.logger.info(
            "Rotated refresh token",
            extra={
                "refresh_id": session_id,
                "successor_id": rotated.id,
                "token_id": rotated.token_id,
            },
        )
        return rotated

    async def _explain_failed_rotation(
        self, session_id: uuid.UUID, now: datetime
    ) -> Exception:
        """
        Why the claiming UPDATE matched nothing — and, for a replay, the
        response to it.

        Runs after the rollback, so everything it reads is re-read from the
        store rather than remembered from before.
        """
        stale = await self.db.get(DatabaseRefreshToken, session_id)
        if stale is None or stale.revoked_at is None:
            self.logger.warning("Expired refresh token", extra={"refresh_id": session_id})
            return RefreshTokenExpired()

        if stale.rotated_to is None:
            # Revoked without a successor: an operator cut this grant, or replay
            # detection did. Not a replay in itself, and re-cutting adds nothing.
            self.logger.warning(
                "Refresh token belongs to a revoked session",
                extra={"refresh_id": session_id},
            )
            return SessionRevoked()

        rotated_ago = (now - (as_utc(stale.revoked_at) or now)).total_seconds()
        if rotated_ago <= REFRESH_ROTATION_GRACE_SECONDS:
            # This client racing itself, not an attacker: parallel requests that
            # all expired at once, or a retry after a network flake. Rejecting
            # without cutting keeps the winner's session — cutting here would
            # take down the pair just handed out and log the hirer out of their
            # own tab.
            self.logger.info(
                "Refresh token re-presented inside the rotation grace window",
                extra={"refresh_id": session_id, "rotated_ago_s": round(rotated_ago, 3)},
            )
            return RotationInProgress()

        self.logger.warning(
            "Refresh token replayed after rotation, cutting the grant's sessions",
            extra={
                "refresh_id": session_id,
                "token_id": stale.token_id,
                "rotated_ago_s": round(rotated_ago, 3),
            },
        )
        token_id = stale.token_id
        await self.revoke_all_for_grant(token_id)
        return RefreshTokenReplayed(token_id)

    async def revoke_all_for_grant(self, token_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(DatabaseRefreshToken)
            .where(
                DatabaseRefreshToken.token_id == token_id,
                DatabaseRefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
            .execution_options(synchronize_session=False)
        )
        revoked = _rowcount(result) or 0
        await self.db.commit()
        self.logger.warning(
            "Revoked refresh sessions", extra={"token_id": token_id, "count": revoked}
        )
        return revoked


# Column bounds. Guards against these and the ChatRequest bound drifting apart
# and raising into a user's chat.
