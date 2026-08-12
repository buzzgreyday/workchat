# Changelog

All notable changes to this project will be documented in this file.

_Versioning: this repo is versioned as a single unit — one tag per release,
covering both frontend and backend together. `backend/pyproject.toml` and
`frontend/package.json` version fields are bumped to match on release, not
tracked independently._

## [0.1.1] - 2026-08-12

### Security

- The system prompt is now added backend-side only and stripped from both the
  JSON and streaming chat responses, so it is no longer part of the history
  returned to clients. A `system` message present in an incoming request is
  dropped rather than forwarded to the model.

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