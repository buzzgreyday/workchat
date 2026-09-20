import hashlib
import hmac

from app.common.config import get_settings


def hash_token(raw_token: str) -> str:
    """
    What gets stored in place of a token.

    Here rather than in a repository because it is HMAC, not persistence: the
    services that mint tokens decide what a stored token looks like, and a
    storage backend only ever sees the result.
    """
    return hmac.new(
        get_settings().token_hashing_secret.encode(), raw_token.encode(), hashlib.sha256
    ).hexdigest()