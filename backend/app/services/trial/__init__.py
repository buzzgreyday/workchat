"""
Guest trials: a few questions for a visitor who has no link.

Every other grant is issued to someone and delivered as a link. A trial is
opened by the visitor themselves, which is what makes it the one way in that a
stranger — or a script — can reach. So it is held by three things, each against
a different abuse, and all checked before a grant exists:

  - a proof-of-work (`pow`), so each trial costs the asker some computing, and
    a script asking for thousands pays for thousands;
  - one trial per address per UTC day, the address kept only as a keyed hash
    that cannot outlive its day (`keys`);
  - a ceiling on trials per day across everyone, so the worst a day of
    strangers can spend is `trial_daily_limit` x `trial_max_queries` questions.

Then it is an ordinary grant — `kind="trial"`, already claimed, opened straight
into a session — and the chat cannot tell it from any other, beyond its access
token saying `knd: "trial"` so the client can word things for a guest.

Off unless TRIAL_ENABLED: both endpoints answer 404 while it is.
"""

import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from app.common.config import Settings
from app.common.crypto import hash_token
from app.common.exceptions import (
    TrialAlreadyUsed,
    TrialBudgetExhausted,
    TrialChallengeInvalid,
    TrialDisabled,
)
from app.common.logging.logging import logger
from app.common.models import Grant, TokenPair
from app.repositories.base import (
    RefreshSessionRepository,
    TokenRepository,
    TrialRepository,
    TrialReservation,
    UserRepository,
)
from app.services.auth import Auth
from app.services.trial import keys, pow
from app.services.trial.pow import Challenge

# The user every trial grant belongs to (created by the migration that added
# trials). The greeting reads the grant's subject, so a guest is "Guest".
TRIAL_USER_NAME = "Guest (trial)"
TRIAL_SUBJECT = "Guest"

__all__ = ["Challenge", "challenge", "start_trial", "TRIAL_SUBJECT"]


def _secret(settings: Settings) -> str:
    """The trial secret, or a 404 if trials are off."""
    if not settings.trial_enabled or not settings.trial_secret:
        raise TrialDisabled()
    return settings.trial_secret


def challenge(settings: Settings) -> Challenge:
    """A fresh proof-of-work for a visitor to solve. Stores nothing."""
    return pow.create_challenge(keys.pow_key(_secret(settings)), settings.trial_pow_max_number)


async def start_trial(
    solution: str,
    address: str,
    *,
    settings: Settings,
    users: UserRepository,
    tokens: TokenRepository,
    sessions: RefreshSessionRepository,
    trials: TrialRepository,
    auth: Auth,
    now: datetime | None = None,
) -> TokenPair:
    """
    Open a trial for this visitor, or say why not.

    The proof-of-work is checked first, because it is the only check that costs
    the asker rather than this server: nothing is read or written for a
    solution that does not hold. Then the store decides address, challenge and
    budget in one durable step, and only then is a grant made.

    Raises TrialDisabled, TrialChallengeInvalid, TrialAlreadyUsed or
    TrialBudgetExhausted.
    """
    secret = _secret(settings)
    now = now or datetime.now(timezone.utc)

    solved = pow.verify_solution(keys.pow_key(secret), solution, now=now.timestamp())
    if solved is None:
        logger.warning("Trial refused: proof-of-work did not hold")
        raise TrialChallengeInvalid()

    day: date = now.date()
    outcome = await trials.reserve(
        day=day,
        ip_hash=keys.address_hash(secret, day, address),
        challenge_hash=solved,
        daily_limit=settings.trial_daily_limit,
    )
    if outcome is TrialReservation.ADDRESS_USED:
        logger.info("Trial refused: this address has had today's")
        raise TrialAlreadyUsed()
    if outcome is TrialReservation.CHALLENGE_USED:
        logger.warning("Trial refused: challenge already spent")
        raise TrialChallengeInvalid()
    if outcome is TrialReservation.BUDGET_SPENT:
        logger.warning("Trial refused: today's trials are all gone", extra={"daily_limit": settings.trial_daily_limit})
        raise TrialBudgetExhausted()

    guest = await users.get_by_name(TRIAL_USER_NAME) or await users.add(
        name=TRIAL_USER_NAME, email=None, phone=None
    )
    grant = await tokens.add(
        Grant(
            id=uuid.uuid4(),
            user_id=guest.id,
            subject=TRIAL_SUBJECT,
            # There is no link, so nothing will ever be presented against this
            # hash; it only has to be unique and unguessable, like any other.
            token_hash=hash_token(secrets.token_urlsafe(32)),
            max_queries=settings.trial_max_queries,
            expires_at=now + timedelta(seconds=settings.trial_ttl_seconds),
            version=2,
            kind="trial",
            claimed_at=now,
        )
    )
    logger.info("Trial opened", extra={"token_id": grant.id})
    return await auth.open_session(grant, sessions)
