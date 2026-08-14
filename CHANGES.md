# Changelog

All notable changes to this project will be documented in this file.

_Versioning: this repo is versioned as a single unit — one tag per release,
covering both frontend and backend together. `backend/pyproject.toml` and
`frontend/package.json` version fields are bumped to match on release, not
tracked independently._

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