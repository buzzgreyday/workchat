import hashlib
import hmac

from app.common.config import TOKEN_HASHING_SECRET


def hash_token(raw_token: str) -> str:
    """
    What gets stored in place of a token.

    Here rather than in a repository because it is HMAC, not persistence: the
    services that mint tokens decide what a stored token looks like, and a
    storage backend only ever sees the result.
    """
    return hmac.new(
        TOKEN_HASHING_SECRET.encode(), raw_token.encode(), hashlib.sha256
    ).hexdigest()