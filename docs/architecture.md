# Architecture

```
Browser  ──►  Caddy  ──►  Next.js frontend        (everything but /api/*)
                     └─►  FastAPI backend  ──►  PostgreSQL
                              │                      (/api/* — prefix stripped)
                              └─►  OpenAI
```

Caddy exists only in production, where it terminates TLS, serves both halves from
one origin and rate-limits per client IP. In development the frontend (`:3000`)
and backend (`:8000`) are exposed directly, which is the one place they are not
same-origin — hence CORS being configured at all.

## A request through the backend

`app/main.py` wires four routers and one exception handler. Middleware is thin on
purpose: `RequestContextMiddleware` is pure ASGI so a correlation id survives a
streaming response, and CORS sits inside it.

```
route handler
  └─ Depends(auth.verify_and_consume)   /chat, /chat/stream — authenticate, spend one query
     Depends(auth.verify)               /session            — authenticate, spend nothing
     Depends(require_admin)             /admin/*            — static header secret
        └─ services/  business logic, raising domain errors
             └─ common/exceptions.py    typed, each carrying its own status
                  └─ main.py handler    the one place an error becomes a response
```

Auth is a **dependency, not middleware** — deliberately, and the reasoning is
recorded in the `app/services/auth.py` module docstring rather than repeated here.
The short version: middleware has no dependency injection, `verify_and_consume`
spends a query and so must not run on a preflight, and the three protected
surfaces need three different checks.

## Layering

| layer | may raise | knows about HTTP |
|---|---|---|
| `app/routes/` | `HTTPException` | yes — this is the boundary |
| `app/services/` | domain errors from `app/common/exceptions.py` | no |
| `app/common/` | domain errors | no |

Services staying HTTP-free is what lets them be tested, and reused, without a
request in flight.

## Where to read next

- **Token flow** — the v1/v2 split, claim and refresh, quota: the
  [Token flow](../README.md#token-flow) section of the README.
- **Schema and retention** — [`database.md`](database.md).
- **Deploying, rate limits, backups** — [`deployment.md`](deployment.md).
