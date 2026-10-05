"""
The trial cookie: this browser has had a guest trial, and when.

The per-address limit resets every UTC day and knows nothing about browsers,
so on its own it lets the same person come back for another trial the next
morning. This is the other half: after a trial, the browser is handed a cookie
for `trial_cookie_days`, and while it carries one no new trial is offered.

Not a tracker, and built so it cannot become one:

  - it holds the date of the trial and a signature, nothing else — no id, so
    there is nothing to link it to on the server, which keeps no record of it;
  - it is signed (HMAC), so it cannot be made up, and only the date on it is
    believed;
  - httpOnly, SameSite=Strict, and only ever read by the trial endpoints.

That is what keeps it inside the ePrivacy exemption for cookies strictly
necessary to a service the visitor asked for — a trial's terms, enforced — so it
needs no consent banner. It can be cleared, like any cookie: it stops casual
repeats, and the daily ceiling is what bounds the cost (see __init__.py).
"""

import hashlib
import hmac
from datetime import date, timedelta


def make(key: bytes, day: date) -> str:
    """The cookie's value for a trial opened on `day`."""
    stamp = day.isoformat()
    return f"{stamp}.{_sign(key, stamp)}"


def remembers(key: bytes, value: str | None, today: date, days: int) -> bool:
    """
    Whether this cookie says the browser had a trial within the last `days`.

    Anything unsigned, malformed or older is read as no cookie at all: a forged
    one cannot claim a trial it did not have, and an expired one is simply
    gone, whatever the browser kept.
    """
    if not value:
        return False
    stamp, _, signature = value.partition(".")
    if not hmac.compare_digest(signature, _sign(key, stamp)):
        return False
    try:
        day = date.fromisoformat(stamp)
    except ValueError:
        return False
    return today - timedelta(days=days) < day <= today


def _sign(key: bytes, stamp: str) -> str:
    return hmac.new(key, stamp.encode(), hashlib.sha256).hexdigest()
