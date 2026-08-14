# Changelog

All notable changes to this project will be documented in this file.

_Versioning: this repo is versioned as a single unit — one tag per release,
covering both frontend and backend together. `backend/pyproject.toml` and
`frontend/package.json` version fields are bumped to match on release, not
tracked independently._

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
