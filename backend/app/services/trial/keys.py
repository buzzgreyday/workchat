"""
The keys a trial is checked with, all from one secret.

Each is the secret under its own label (HMAC), so none can stand in for
another, and none reveals the secret: the proof-of-work's signing key cannot
hash an address, and today's address key cannot hash tomorrow's.
"""

import hashlib
import hmac
import ipaddress
from datetime import date


def _derive(secret: str, label: str) -> bytes:
    return hmac.new(secret.encode(), f"workchat:trial:{label}".encode(), hashlib.sha256).digest()


def pow_key(secret: str) -> bytes:
    """What proof-of-work challenges are signed with."""
    return _derive(secret, "pow")


def address_hash(secret: str, day: date, address: str) -> str:
    """
    An address, as the trial store keeps it: an HMAC under a key for one UTC day.

    Enough to say whether the same address has had a trial today, and nothing
    more. The key is a function of the day, so a hash from yesterday cannot be
    matched against one from today — the store cannot follow a visitor across
    days even with every row it ever held — and once its day is over a hash
    belongs to a key nothing will compute again. Not reversible by guessing
    either, as a plain hash of an IPv4 address would be in seconds: the key is
    secret.
    """
    key = _derive(secret, f"ip:{day.isoformat()}")
    return hmac.new(key, normalise_address(address).encode(), hashlib.sha256).hexdigest()


def normalise_address(address: str) -> str:
    """
    The part of an address that names one visitor.

    IPv4 as it is. IPv6 cut to its /64: a home or a phone is handed a whole /64
    and may use any address in it, so the full address would give one visitor
    as many trials as they cared to rotate through. An IPv4 address carried in
    IPv6 is read as the IPv4 address it is. Anything unparseable is kept as
    given, so it still counts as one address rather than none.
    """
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        return address.strip()
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network(f"{ip}/64", strict=False))
    return str(ip)
