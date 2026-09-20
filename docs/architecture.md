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

`app/factory.py` wires four routers and one exception handler; `app/main.py` is
the ASGI entrypoint that calls it, and nothing else. The split is what keeps
importing the application free of configuration — building a `FastAPI` reads
`DEV_MODE` and the CORS list, so a module that built one at import demanded a
configured environment from anything that touched it, tests included.

Middleware is thin on purpose: `RequestContextMiddleware` is pure ASGI so a
correlation id survives a streaming response, and CORS sits inside it.

```
route handler
  └─ Depends(verify_and_consume)  /chat/stream  — authenticate, spend one query
     Depends(verify)              /session      — authenticate, spend nothing
     Depends(require_admin)       /admin/*      — static header secret
        └─ services/  business logic, raising domain errors
             └─ common/exceptions.py    typed, each carrying its own status
                  └─ factory.py handler  the one place an error becomes a response
```

Auth is a **dependency, not middleware** — deliberately, and the reasoning is
recorded in the `app/services/auth.py` module docstring rather than repeated here.
The short version: middleware has no dependency injection, `verify_and_consume`
spends a query and so must not run on a preflight, and the three protected
surfaces need three different checks.

Those three are the adapter for `Auth`, which itself takes plain arguments and
declares no `Depends`. That is what makes `dependency_overrides[get_auth]` reach
every endpoint at once — and what lets `Auth` be built and called in a test with
no request in flight.

## A chat turn

Chat is streaming-only, and the turn is a pipeline of generators rather than an
object:

```
run_turn()      the model, the tool rounds, the reply  ->  domain events
  └─ recorded() passes them through, writes the transcript
       └─ route encodes each event as an SSE frame
```

Nothing in `app/services/chat/` mentions SSE and nothing in the route mentions
OpenAI. That split is the reason there is one loop: while the transport was
baked into it there were two — one yielding frames, one building a JSON body —
and six things were duplicated between them.

Everything a turn accumulates lives in generator locals, so a second call cannot
inherit the first one's reply or tool counts. The previous class kept them on
the instance and relied on the route building a fresh one per request.

`ToolInvoked` and `RoundFinished` are emitted but never reach a client. They are
how the recorder knows what a turn did when it is aborted and the terminal event
never arrives — the job the mutable attributes used to do.

Searching the CV (`app/services/search.py`) imports no vendor SDK. What the model
is shown and told about those results — the schemas, the JSON encoding, the
prose steering it toward opening an entry rather than answering from a summary —
is the adapter's, in `app/services/chat/tooling.py`.

Where the records come from is a third thing again, in `app/services/indexing.py`:
the backend scans `backend/resources/` at startup, parses each file's frontmatter
and holds the corpus in memory. There is no build step and no artifact — twenty
files and ~46 KB of markdown cost milliseconds to read, and an index that only
exists in the process that serves it cannot go stale against one. A scan that
finds no records stops the server before it binds a port.

### Configuration

`Settings` is a frozen dataclass built by `get_settings()`, cached for the
process. Nothing reads the environment at import: `require_env` raising is what
a missing secret looks like, and it should happen where a server is being
started rather than where a module is being imported.

Values that consult no environment stay module constants in `app/common/config.py`,
because they are facts about the application rather than settings — the signing
algorithm, the tool-round cap, the cookie path. `REFRESH_COOKIE_NAME` is there
too for a different reason: `/v2/auth/refresh` declares it as a `Cookie` alias,
and FastAPI builds a route's parameter model when the route is declared, so the
name has to exist at import or not at all.

## Layering

| layer | may raise | knows about HTTP |
|---|---|---|
| `app/routes/` | `HTTPException` | yes — this is the boundary |
| `app/services/` | domain errors from `app/common/exceptions.py` | no |
| `app/repositories/` | domain errors | no |
| `app/common/` | domain errors | no |

Services staying HTTP-free is what lets them be tested, and reused, without a
request in flight.

`app/repositories/` is persistence as its own layer, and the only layer allowed
to know what the storage engine is.

A repository speaks in the domain models from `app/common/models/`, never the
ORM rows in `app/common/schemas.py`, and takes no session in its abstract
methods — so a service that depends on `UserRepository` can be exercised
against an in-memory implementation with no database in the process.

```
app/repositories/
├── base.py       the contract: UserRepository, TokenRepository,
│                 RefreshSessionRepository, TranscriptRepository,
│                 ConversationRepository
├── sql/          the SQLAlchemy backend — the only package naming a session
│   ├── __init__.py    its providers, and the package's front door
│   ├── _shared.py     private: result and column helpers
│   ├── user.py        one module per aggregate, named for the table
│   ├── token.py       it owns rather than the class inside it
│   ├── refresh_session.py
│   ├── transcript.py  the write half of the chat tables
│   └── conversation.py  and the read half
└── __init__.py   the composition root: binds a backend, exports the providers
```

The abstraction takes the plain name and the implementation is qualified —
`TokenRepository` is what a caller annotates, `SQLTokenRepository` is one way of
being one. `RefreshSessionRepository` is spelled out because `session` already
means a SQLAlchemy `AsyncSession` in these files, and the two appear together.

`transcript` and `conversation` cover the same two tables on purpose. They are
split by session ownership, not by data: the recorders have to outlive the
request that started them, the admin reads run inside one, and a single
abstraction claiming both would have to lie about that somewhere.

**There is deliberately no `commit` anywhere in `base`, and no unit of work.**
SQLAlchemy's `Session` is already a unit of work, so wrapping it in another one
would only add a verb other stores cannot honour: a file-write backend has no
rollback in any meaningful sense, and Mongo without a replica set has no
multi-document transaction and is already durable on an acknowledged write.
Either would have to stub a `commit` whose name implies a guarantee it cannot
keep.

Instead, repositories flush and `get_db` commits when the request ends cleanly,
rolling back when it does not. A service writes through repositories and says
nothing about durability. SQL still gets one transaction per request — FastAPI
caches `Depends(get_db)`, so every repository in a request shares a session —
but as a property of that backend, never something a service claims.

`get_user_repository` and `get_token_repository` are FastAPI dependencies whose
*own* dependencies are whatever the chosen backend declares. The SQL providers
ask for `Depends(get_db)`; a backend needing something else, or nothing, says so
there, and the route asking for a repository is unaffected either way. That is
what makes another store a new package plus a one-line change in `__init__.py`,
rather than an edit to every route and service.

### When the transaction actually ends

Nothing in a service commits, which is worth tracing once because the answer is
spread across three files. Issuing a token is the example: `issue_token`
(`app/services/admin.py`) writes a user and a grant and never mentions
durability.

```
route  Depends(get_user_repository)  ─┐
       Depends(get_token_repository) ─┤  both providers declare
                                      └─ Depends(get_db)   ← resolved ONCE
                                           └─ transaction(async_session)
                                                yield  → the request runs
                                                else:  → session.commit()
                                                except:→ session.rollback()
```

FastAPI caches a dependency for the life of a request, so `get_db` resolves once
and every repository is handed the *same* `AsyncSession`, and therefore the same
transaction. `users.add` and `tokens.add` only `flush()` — which is what assigns
`user.id` so the grant can reference it — and the commit fires when the request's
exit stack unwinds, in `transaction` (`app/common/db.py`). If the grant insert
fails, the user insert rolls back with it, because it was never a separate
transaction.

Two consequences that are easy to rediscover the hard way:

- **A streaming response still commits.** A dependency with `yield` registers on
  the request's exit stack, not the handler's, and the response is sent inside
  that stack — so for `/chat/stream` the session outlives the streamed body.
- **The transcript recorder cannot use any of this**, which is what
  `get_session_factory` is for. On client abort it runs *after* the request
  session is closed, so it opens its own scope; writing through the request's
  would be a use-after-close.

Where an operation is genuinely transactional on its own — `rotate` inserts a
successor and conditionally revokes its predecessor, so a lost race leaves no
orphan — the atomicity is internal to one repository method, which owns it
privately with whatever its backend has. Nothing needs two repositories to
share a transaction beyond the shared-session property above.

### What a request costs

Counted, not estimated — `SQL_ECHO=1` and the correlation id that every log line
already carries. Connection setup is excluded; these are steady-state figures.

| path | statements | commits |
|---|---|---|
| `POST /chat/stream` — v2, continuing a conversation | 7 | 3 |
| `POST /chat/stream` — v1, continuing a conversation | 6 | 3 |
| `POST /chat/stream` — first message of a conversation | +1 | 3 |
| `POST /v2/auth/refresh` | 5 | 1 |
| `POST /v2/auth/claim` | 3 | 2 |
| `GET /session` — v2 | 2 | 1 |

A v2 chat message is one session read, one atomic spend, and five transcript
statements. **Only the first is a question a token claim could answer** — the
transcript is the product, not authentication, and no token design removes it.

This comes up because a JWT is supposed to avoid lookups, and at a glance the
backend seems to do a lot of them anyway. The short answer is that the lookups
which remain are state a token cannot hold: how many questions are left, whether
this conversation belongs to you, what was asked.

**The spend does four checks for free.** `consume_query` puts
`revoked_at IS NULL`, `expires_at > now`, `used_queries < max_queries` and
`version = expected` into the predicate of the `UPDATE … RETURNING` it had to
run anyway. The obvious implementation — read the grant, check in Python, write
— is three statements and a lost-update race. Revocation, expiry, quota and
version therefore cost nothing extra.

**The claims earn their place.** `ver` separates v1 from v2 with no lookup;
`typ` rejects the wrong kind of token before any query; `tid` carries the grant
id so nothing has to search for it; and a refresh token's `jti` *is* its row id,
so rotation is a primary-key update rather than a lookup by token hash. The one
piece of vestige is `max_queries`, minted into v1 tokens and never read — the
quota always comes from the grant row.

**The session read is the only discretionary call**, and it buys less than it
looks. Grant revocation is already caught by the spend, so `_require_live_session`
only makes a *session*-level cut — the kind replay detection triggers — take
effect immediately rather than within the access token's remaining ≤15 minutes.
It stays: it is a primary-key read on a path where the same request spends one
to six OpenAI round trips at roughly a second each.

**Three transactions is not an accident.** The spend commits before the answer
streams, or an aborted stream hands back free questions. The question commits
before the model runs, or a crashed turn loses what was asked. The reply cannot
commit before the stream ends, because that is when it exists.

**`refresh` reads `refresh_tokens` twice.** The caller loads the session to check
its hash, and `rotate` loads it again to check it exists. That is
`RefreshSessionRepository.rotate` declining to trust that its caller checked —
the contract says it owns the race — and it costs one primary-key read per
rotation, which is once per access-token lifetime per client.

## Where to read next

- **Token flow** — the v1/v2 split, claim and refresh, quota: the
  [Token flow](../README.md#token-flow) section of the README.
- **Schema and retention** — [`database.md`](database.md).
- **Deploying, rate limits, backups** — [`deployment.md`](deployment.md).
