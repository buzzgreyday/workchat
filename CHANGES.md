# Changelog

All notable changes to this project will be documented in this file.

_Versioning: this repo is versioned as a single unit — one tag per release,
covering both frontend and backend together. `backend/pyproject.toml` and
`frontend/package.json` version fields are bumped to match on release, not
tracked independently._

## [0.5.0] - 2026-09-20

### Removed

- `python -m app.build_index` is gone, and so is `resources/index.json`. What
  remains of that script is `python -m app.build_skills`, which only regenerates
  the skills list inside `skills.md` — a tracked file, produced locally and
  committed like any other source. The server never runs it.

  Deployment lost two steps with it. There is no index to build after a release,
  and no `chown -R 1000:1000 backend/resources` to remember beforehand, because
  nothing in the container writes to that directory any more; in production it
  is now mounted read-only. Updating is `git pull` and `up -d --build`, which is
  what the deploy workflow already ran.

### Changed

- The CV index is built by the process that serves it. On startup the backend
  scans `backend/resources/`, parses the frontmatter of every markdown file and
  holds the corpus in memory. The records, their order and the ranking are
  unchanged — what is gone is the step between editing a CV file and the site
  knowing about it.

  Forgetting that step was the failure. The index was a gitignored artifact
  built by hand, and the deploy never built it, so a release that changed any CV
  record left the site answering from the previous one — with `/health` passing
  throughout, so nothing surfaced the staleness. The index was never expensive
  enough to be worth an artifact: twenty files and about 46 KB of markdown, with
  no embeddings and no API calls behind it, read in milliseconds.

  A record that will not parse is skipped with its name in the log rather than
  taking the other nineteen with it. A resources directory that yields nothing
  at all stops the server before it binds a port, so the container never reports
  healthy and a deploy that shipped a broken mount fails instead of going live
  with nothing to answer from.

  The markdown is read in the same pass that parses the frontmatter, so the
  first search of a running server touches no disk, and a record nobody can read
  surfaces at boot rather than on the one question that needed it.

  Editing a record on a running server still needs a restart — the corpus is
  read once. In development that is automatic: the resources directory is
  watched, so a saved edit reloads the app and rebuilds the index.

- Decoding a token produces typed claims rather than a bare dict. `decode()`
  returned `dict`, so the type of every v2 claim was `Any` through the paths
  that decide who may spend a hirer's quota. The claims are their own model now,
  deliberately not the one used to mint tokens: that one defaults `max_queries`
  to 20, which would invent a quota for a token carrying none, and types `typ`
  as a literal, which would turn an unrecognised token type into a parse failure
  where the service wants to answer "not an access token".

  Nothing about a v1 token's shape is tightened — every field is optional, and
  those links are in inboxes and on printed QR codes. A `ver` that is a boolean,
  a string or a float is now refused rather than read as version 1; no token
  this service signs carries one, and both answers were already 401.

- The admin write endpoints return response models instead of hand-built JSON,
  so their output is validated and the ids are serialised rather than converted
  by hand. Issuing a token still builds its own response, because it is the one
  endpoint that answers in two media types.

### Fixed

- A hirer's contact details and a grant's `token_hash` no longer reach the log.
  Issuing one token wrote the email and phone five times and the hash once, all
  at INFO and so all of it in production — while the same codebase keeps chat
  message text behind a flag at debug, because logging that was judged
  unacceptable. Contact details were held to no standard at all.

  The hash is the worse half: it is what a bearer is authenticated against, so a
  log holding it holds the verifier for every token on the grant. The issue path
  logs identifiers now — `token_id`, `user_id`, `company` — and a redaction
  filter on the log handler drops a deny-list of field names wherever they
  appear, including nested inside a record-shaped payload. The call sites are
  already written not to pass them; the filter is what stops the next one, since
  a log is the only store here with no retention policy and no redaction path.

- SQL echo is its own opt-in rather than following `DEV_MODE`. It writes every
  statement and its bound parameters to the log, which on the issue path meant
  the same email, phone and hash again — in the message rather than the
  structured fields, where the redaction filter cannot reach them. Every local
  session was doing it by default. `SQL_ECHO=1` turns it back on for debugging a
  query.

## [0.4.0] - 2026-09-19

### Removed

- `POST /chat` is gone; chat is streaming-only. Nothing in the browser used it —
  the client has always called `/chat/stream` — and keeping a second endpoint
  meant keeping a second implementation of the same tool-calling loop, which is
  where the duplication this release removes came from. The eval harness now
  reads the stream, and the dead `send()` path went with it.

### Changed

- The chat service is a pipeline of generators rather than a class. A turn
  yields domain events; a recorder passes them through and writes the
  transcript; the route encodes them as SSE frames. Nothing in the service
  mentions SSE and nothing in the route mentions OpenAI — which is what makes
  one loop enough where there were two.

  Everything a turn accumulates now lives in generator locals, so a second turn
  cannot inherit the first one's reply or tool counts. The previous class kept
  them on the instance and relied on a fresh one being built per request.

- Searching the CV no longer imports the OpenAI SDK. What the model is shown and
  told about the results — the schemas, the JSON encoding, the prose steering it
  toward opening an entry rather than answering from a summary — moved to an
  adapter beside the chat service. The index and the markdown it reads are now
  cached rather than re-read on every search.

### Fixed

- A reply that fails mid-stream now says so. The client receives an error frame
  instead of a stream that simply stops, which was indistinguishable from a
  dropped connection; the reason is logged server-side rather than shown.

- An empty assistant message is no longer stored and echoed back, so a turn that
  produced no text stops appearing as a blank entry in the next question's
  history.

- A tool call the service cannot run is dropped rather than assembled. The
  non-streaming path filtered these and warned; the streaming path never looked,
  and there is only one path now.

## [0.3.0] - 2026-09-19

### Changed

- Persistence moved behind a repository layer. `app/services/db.py` — which had
  grown to hold every query in the app — is gone, replaced by
  `app/repositories/`: a contract stated in domain terms, and an `sql/` package
  that is the only place naming SQLAlchemy. `AsyncSession` now appears in two
  files rather than nine, and no ORM row crosses into a route or a service.

  There is deliberately no unit of work and no `commit` in any abstraction. A
  SQLAlchemy `Session` is already one, and a store without transactions could
  only stub a `commit` while implying a guarantee it cannot keep. Instead the
  request owns its transaction and repositories flush — except for a named few
  that are durable on return, because a spend a later failure could undo is a
  free question.

- The chat model is configurable per environment. Development defaults to
  gpt-4.1-nano, where the question is whether the tool round-trip works rather
  than whether the answer is good; production still gets gpt-4.1-mini, which
  measurably answers depth questions better. `OPENAI_MODEL` overrides either.

### Fixed

- Conversation message counts no longer lose turns. The count was incremented in
  Python against a stale read, so two turns arriving together both wrote the same
  value and one was lost — five concurrent questions recorded two. The database
  computes the increment now.

- Listing conversations stopped issuing a query per row. A page of fifty cost a
  hundred and one round trips, all to fetch two truncated preview strings; it is
  one windowed query now.

- Refreshing a token can no longer fail while notifying the operator. Replay
  detection rolled back a session whose rows the caller still held, so reading
  the grant's owner afterwards risked lazy IO outside the async context; the
  caller now holds a plain value that no rollback can expire.

## [0.1.13] - 2026-08-14

### Changed

- The agent runs on gpt-4.1-mini. Retrieval had stopped being the limiting
  factor: over 26 questions x 3 runs the previous model scored 22-24 against
  mini's 25-26, and its remaining failures were all cases where it fetched the
  right record and could not pull the fact out of it. It also never once worked
  out how long a role has run — "how long has he been at iEDI" got "since
  September 2025" in every arm ever measured — where mini answers it. Costs
  about a second more per reply.

### Fixed

- Asked to elaborate, the agent reads the record instead of paraphrasing its
  summary. Search results now say which records carried every word of the query
  and ask for those to be opened, and say plainly that "tell me more", "why" and
  "elaborate" cannot be answered from a summary. Questions whose answers appear
  only in a record body went from 2 of 6 to 6 of 6, and the agent now opens a
  record for 22 of 26 questions rather than roughly 1 in 20 — while still not
  bothering when nothing matched.

- A record is found whatever the case of its filename. The model retypes the
  name out of the search result and sometimes alters it — asking for "iEDI.md"
  when the file is "iedi.md" — which returned "no such file" and, being
  indistinguishable from the record not existing, sent it back to the summary.

### Added

- Eval probes for depth: six questions whose answers exist only inside a record
  body, since every earlier question could be answered from a summary and so
  could not measure whether the agent ever opens anything.

## [0.1.12] - 2026-08-14

### Fixed

- The agent no longer denies things the CV plainly contains. Asked whether
  Michael had ever simplified despatch advices, it replied that there was no
  record — while iedi.md describes the redesign outright. Two causes, both now
  addressed: search results were unranked, so the record matching every word of
  a query sat among records that merely share one common word; and the cases
  themselves lived inside large role records whose summaries could not represent
  them. Measured over 20 questions x 3 runs, wrong answers fell from 6-7 to 1.

- Search results are ordered best-first, each carrying how much of the query it
  matched. Unranked, an eleven-record result read as noise and the agent
  answered from whichever summary came first.

- Common words no longer decide a result. Matching is OR'd and substring-based,
  so "at" on its own matched every record in the CV — it sits inside
  "integrations" — and a question like "despatch advices at iEDI" came back
  claiming the whole CV was relevant.

- A hiring manager gets an answer when the tool-call budget runs out. Exhausting
  MAX_TOOL_ROUNDS ended the turn on whatever had been streamed, which for a model
  still asking for tools is nothing at all: an empty reply. One further call with
  tools disabled now yields a thinner answer built from what was already fetched.

### Added

- Per-case CV records, so a case has a summary that describes it rather than
  being buried in a role: the despatch advice redesign, the customer API
  consolidation, and the Kubernetes to Nomad migration.

- backend/evals: a 20-question harness that scores the agent on wrong denials,
  invented answers and missed facts, and attributes every failure to the
  retrieval step that caused it. It is what these numbers come from, and it
  re-scores saved runs when the scoring changes, so past results stay comparable.

## [0.1.11] - 2026-08-14

### Fixed

- No gender is hardcoded in application code (frontend has my name harcoded though). 
  The frontend however needs some additional tweeks, so we're saving this for later.
  This was more work than expected, but this is a good place to leave it for now and iterate.

## [0.1.10] - 2026-08-14

### Fixed

- The agent knows what day it is. It was reasoning from its training cutoff,
  telling hirers "today is in early 2025" and miscalculating how long Michael
  has been at iEDI.

## [0.1.9] - 2026-08-14

### Added

- The conversation list now shows the agent's latest reply beside the question,
  so a wrong answer is visible without opening each conversation.

### Removed

- The "questions are stored" notice in the chat UI.

## [0.1.8] - 2026-08-14

### Fixed

- The agent no longer opens with a claim of microservices experience before
  correcting itself; the tag that suggested it is gone, and the record is still
  found by search.

## [0.1.7] - 2026-08-14

### Added

- Chat turns are now stored, so it is possible to see what hirers actually asked
  and what the agent answered. Readable via `GET /admin/conversations`, content
  scrubbed after 30 days.

### Changed

- Logs are structured JSON and carry a request id. `extra={...}` fields were
  previously discarded by the format string; message content stays out of logs
  and lives only in the database.

### Fixed

- `search_cv` reports when nothing matched instead of returning the whole CV,
  which the model could not tell apart from a precise hit and answered from by
  inference.
- The iEDI record now states its architecture — a monolith surrounded by
  customer-tailored APIs — and describes RabbitMQ's actual, partial role.

## [0.1.6] - 2026-08-14

### Changed

- CV records now carry the vocabulary a hiring manager would actually search
  for, and the orphaned records are reachable by link.

## [0.1.5] - 2026-08-14

### Added

- A Frameworks and Tools record, and the real iEDI stack on the experience
  record it was missing from.

## [0.1.4] - 2026-08-14

### Fixed

- Long unbroken text no longer overflows the message bubble.

## [0.1.3] - 2026-08-14

### Fixed

- The chat window is no longer overlapped by the mobile browser's URL bar.

## [0.1.1] - 2026-08-12

### Security

- The system prompt is now added backend-side only and stripped from both the
  JSON and streaming chat responses, so it is no longer part of the history
  returned to clients. A `system` message present in an incoming request is
  dropped rather than forwarded to the model.
- The non-streaming chat path now bounds tool-call rounds with
  `MAX_TOOL_ROUNDS`, shared with the streaming path, instead of looping without
  an upper limit.

### Fixed

- Streaming `done` event repeated the assistant reply: the message was appended
  once by the streaming loop and again when building the final history.

## [0.1.0] - 2026-08-11

### Added

- Initial

### Changed

- Initial

### Fixed

- Initial

### Security

- Initial

<!--
When cutting a release, move the relevant items above into a new section:

## [0.1.0] - YYYY-MM-DD
### Added
### Changed
### Fixed
### Security
-->
