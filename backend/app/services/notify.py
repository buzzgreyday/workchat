"""
Where operator-facing events go.

Log-only today. The events it carries all mean the same thing in practice — a
hirer can no longer reach the chat and needs a fresh link — and the agent tells
them so itself, so nothing here is on the hirer's critical path.

It is a class with one method per event rather than bare `logger.warning` calls
at the call sites so that pointing it at an inbox later is a change to this file
alone. Same reason nothing here may raise: a notification failing must never
turn into a 500 on someone's auth request.
"""

import uuid

from app.common.logging.logging import logger


class Notifier:
    async def claim_link_reused(
            self,
            token_id: uuid.UUID,
            subject: str,
            company: str | None,
    ) -> None:
        """A spent claim link was presented again. Usually the hirer switching
        device or clearing site data, occasionally a leaked URL being tried."""
        logger.warning(
            "Claim link reused after it was spent — this hirer needs a new link",
            extra={"token_id": token_id, "subject": subject, "company": company},
        )

    async def sessions_cut(
            self,
            token_id: uuid.UUID,
            subject: str,
            company: str | None,
            reason: str,
    ) -> None:
        """Every session on a grant was revoked. With a single-use claim there is
        no way back in from the hirer's side, so this always needs a new link."""
        logger.warning(
            "Sessions cut — this hirer needs a new link",
            extra={"token_id": token_id, "subject": subject, "company": company, "reason": reason},
        )


notifier = Notifier()
