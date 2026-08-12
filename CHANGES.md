# Changelog

All notable changes to this project will be documented in this file.

_Versioning: this repo is versioned as a single unit — one tag per release,
covering both frontend and backend together. `backend/pyproject.toml` and
`frontend/package.json` version fields are bumped to match on release, not
tracked independently._

## [Unreleased]

### Fixed

- CV records now state whether the code they describe is actually live. Asked
  whether anything besides this chat app was running, the agent offered the
  .NET API — a local learning exercise that was never deployed — while missing
  the Constellation SDK, which is published on PyPI as `pypergraph-dag`.
  `search_cv` returns only the index summaries, so liveness is recorded in each
  record's frontmatter `summary` as well as in a `## Status` section in the
  body, and every experience/project record now carries one.

- `build_index` now breaks ranking ties on the tag name. Equal-scoring tags
  previously fell back to `rglob()` insertion order, i.e. filesystem order, so
  regenerating `skills.md` on another machine reshuffled the file without any
  tag actually changing.

### Changed

- Regenerated the auto-generated skills section in `skills.md`, which was stale
  and missing the `grafana`, `loki` and `tempo` tags.

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