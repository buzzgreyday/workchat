"""
A proof-of-work, to make asking for a trial cost a script something.

The shape ALTCHA uses (altcha.org), written here rather than taken as a
dependency because the whole of it is a dozen lines of hashlib: the server picks
a secret number and publishes `challenge = sha256(salt + number)`; the browser
finds the number by trying them in turn, on average half of `maxnumber` hashes —
well under a second for a person, a real cost per trial for anyone asking for
thousands. No third party sees the visitor, and nothing is stored to check it:

  - the challenge is signed (HMAC), so a client cannot make up an easy one;
  - the salt carries its own expiry, under the signature, so an old solution
    cannot be banked and spent later;
  - the trial store keeps each challenge that paid for a trial, so one solution
    opens one trial.
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from pydantic import BaseModel

ALGORITHM = "SHA-256"
# Long enough to solve on a slow phone, short enough that a solution is not
# worth stockpiling.
CHALLENGE_TTL_SECONDS = 300


class Challenge(BaseModel):
    """What the browser is given to solve. The field names are ALTCHA's."""

    algorithm: str = ALGORITHM
    challenge: str
    maxnumber: int
    salt: str
    signature: str


def create_challenge(key: bytes, max_number: int, now: float | None = None) -> Challenge:
    expires = int((now if now is not None else time.time()) + CHALLENGE_TTL_SECONDS)
    salt = f"{secrets.token_hex(12)}?expires={expires}"
    number = secrets.randbelow(max_number + 1)
    challenge = _sha256(f"{salt}{number}")
    return Challenge(
        challenge=challenge,
        maxnumber=max_number,
        salt=salt,
        signature=_sign(key, challenge),
    )


def verify_solution(key: bytes, payload: str, now: float | None = None) -> str | None:
    """
    The challenge a solution answers, if it holds; None if it does not.

    `payload` is base64 of the JSON the browser sends back: the challenge as
    given plus the `number` it found. Returning the challenge rather than True
    is what lets the caller spend it, so the same solution cannot pay twice.

    Every check is made, and every comparison is constant-time, so how long a
    refusal takes says nothing about which check refused.
    """
    solution = _decode(payload)
    if solution is None:
        return None
    try:
        algorithm = str(solution["algorithm"])
        challenge = str(solution["challenge"])
        number = int(solution["number"])
        salt = str(solution["salt"])
        signature = str(solution["signature"])
    except (KeyError, TypeError, ValueError):
        return None

    signed = hmac.compare_digest(signature, _sign(key, challenge))
    solved = hmac.compare_digest(challenge, _sha256(f"{salt}{number}"))
    current = _expires(salt) > (now if now is not None else time.time())
    if algorithm == ALGORITHM and signed and solved and current and number >= 0:
        return challenge
    return None


def _decode(payload: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(base64.b64decode(payload, validate=True))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _expires(salt: str) -> int:
    """The expiry the salt carries, or 0 — already past — if it carries none."""
    _, _, query = salt.partition("?")
    for part in query.split("&"):
        name, _, value = part.partition("=")
        if name == "expires" and value.isdigit():
            return int(value)
    return 0


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _sign(key: bytes, challenge: str) -> str:
    return hmac.new(key, challenge.encode(), hashlib.sha256).hexdigest()
