"""
Request correlation middleware.

Pure ASGI on purpose. BaseHTTPMiddleware runs the downstream app in a separate
anyio task, which forks the context — ContextVars set inside the request would
not be visible here, and correlation would break across the streaming body,
silently and only in production. A plain ASGI callable keeps one task and one
context for the whole request, streaming included.
"""
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.context import (
    conversation_id_var,
    new_request_id,
    request_id_var,
    token_sub_var,
)

REQUEST_ID_HEADER = b"x-request-id"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = None
        for key, value in scope.get("headers", []):
            if key.lower() == REQUEST_ID_HEADER:
                inbound = value.decode("latin-1")[:32] or None
                break

        request_id = inbound or new_request_id()
        request_token = request_id_var.set(request_id)
        conversation_token = conversation_id_var.set(None)
        sub_token = token_sub_var.set(None)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((REQUEST_ID_HEADER, request_id.encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_var.reset(request_token)
            conversation_id_var.reset(conversation_token)
            token_sub_var.reset(sub_token)
