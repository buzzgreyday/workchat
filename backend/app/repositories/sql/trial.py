"""The trial_requests and trial_budget tables — guest trials, by day."""

from datetime import date

from sqlalchemy import ColumnElement, delete, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import DatabaseTrialBudget, DatabaseTrialRequest
from app.repositories.base import TrialRepository, TrialReservation


class SQLTrialRepository(TrialRepository):
    """The trial tables, behind TrialRepository."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    async def reserve(
        self, day: date, ip_hash: str, challenge_hash: str, daily_limit: int
    ) -> TrialReservation:
        # Earlier days first. Their hashes were made under keys that no longer
        # exist, so they can match nothing; keeping them would only be keeping
        # data. Rolled back with the rest if this request is refused, and done
        # by the next one instead.
        await self.db.execute(delete(DatabaseTrialRequest).where(DatabaseTrialRequest.day < day))

        # The cheap refusals, read before anything is spent. The unique
        # constraints below still decide a race; these only spare the budget
        # an increment that would have to be taken back.
        if await self._exists(DatabaseTrialRequest.day == day, DatabaseTrialRequest.ip_hash == ip_hash):
            return TrialReservation.ADDRESS_USED
        if await self._exists(DatabaseTrialRequest.challenge_hash == challenge_hash):
            return TrialReservation.CHALLENGE_USED

        # The day's counter, created on its first trial. ON CONFLICT DO NOTHING
        # so two first trials of a day cannot both try to create it.
        await self.db.execute(
            self._insert(DatabaseTrialBudget)
            .values(day=day, issued=0)
            .on_conflict_do_nothing(index_elements=["day"])
        )
        # The ceiling, held by one statement: the increment only happens while
        # there is room, so two trials racing for the last place cannot both
        # get it.
        taken = await self.db.execute(
            update(DatabaseTrialBudget)
            .where(DatabaseTrialBudget.day == day, DatabaseTrialBudget.issued < daily_limit)
            .values(issued=DatabaseTrialBudget.issued + 1)
            .returning(DatabaseTrialBudget.issued)
            .execution_options(synchronize_session=False)
        )
        if taken.scalar_one_or_none() is None:
            return TrialReservation.BUDGET_SPENT

        self.db.add(DatabaseTrialRequest(day=day, ip_hash=ip_hash, challenge_hash=challenge_hash))
        try:
            await self.db.flush()
        except IntegrityError:
            # A twin request won the race between the reads above and here.
            # The session is spoiled either way; the caller's refusal rolls it
            # back, and the budget increment with it.
            return (
                TrialReservation.ADDRESS_USED
                if await self._exists_after_rollback(day, ip_hash)
                else TrialReservation.CHALLENGE_USED
            )

        # Durable before returning, like a spent question: a trial the rest of
        # the request could undo would be a free one.
        await self.db.commit()
        self.logger.info("Guest trial reserved", extra={"day": day.isoformat()})
        return TrialReservation.RESERVED

    async def _exists(self, *where: ColumnElement[bool]) -> bool:
        result = await self.db.execute(select(DatabaseTrialRequest.id).where(*where).limit(1))
        return result.first() is not None

    async def _exists_after_rollback(self, day: date, ip_hash: str) -> bool:
        await self.db.rollback()
        return await self._exists(DatabaseTrialRequest.day == day, DatabaseTrialRequest.ip_hash == ip_hash)

    def _insert(self, table: type[DatabaseTrialBudget]) -> postgresql.Insert | sqlite.Insert:
        """
        INSERT with ON CONFLICT, in this connection's dialect.

        Both have it, under the same name, but each in its own module: the one
        statement here that is not portable SQLAlchemy core.
        """
        dialect = self.db.get_bind().dialect.name
        return (postgresql.insert if dialect == "postgresql" else sqlite.insert)(table)
