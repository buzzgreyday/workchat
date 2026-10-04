"""
Where a request came from, as far as this backend can honestly tell.

Behind the Caddy this repo ships, the socket peer is always Caddy, and the
visitor's address is in X-Forwarded-For — which Caddy writes itself, replacing
anything a client sent, since it trusts no proxy in front of it. So the header
is believed only when TRUST_PROXY_HEADERS says that is the deployment, and then
only its last entry, the one the proxy nearest this backend added. Anywhere
else — dev, where port 8000 is published — the header is whatever a client
chose to send, and the peer is the truth.

Used to tell guest trials apart, never logged: an address is personal data,
and the trial store only ever sees a keyed hash of it (services/trial/keys.py).
"""

from fastapi import Request

from app.common.config import get_settings


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"
