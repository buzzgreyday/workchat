---
title: AI CV Chat Application
type: project
tags: [python, fastapi, typescript, nextjs, react, postgresql, sqlalchemy, alembic, docker, full-stack, full-stack-developer, backend, frontend, rest-api, jwt, openai, tailwind, tool-calling, llm, software-engineer, security, authentication, sse, server-sent-events, streaming, async, concurrency, bash, shell-scripting, caching]
dates: "2026-"
summary: "This chat application itself — a full-stack AI-powered CV assistant (FastAPI/PostgreSQL backend, Next.js/TypeScript frontend, Dockerized) that lets hiring managers query Michael's CV through a tool-calling LLM agent instead of a static resume. BUILT BY MICHAEL: his own project, not a third-party product - the tool the hirer is using is itself one of his work samples. LIVE: deployed and serving this conversation."
---

## Technologies
Backend: Python, FastAPI, SQLAlchemy (async), Alembic migrations, PostgreSQL, JWT-based access tokens, OpenAI tool-calling.
Frontend: Next.js, React, TypeScript, Tailwind CSS.
Infrastructure: Docker Compose, Caddy reverse proxy with automatic HTTPS.

## What it does
- The chat interface a hiring manager is using right now: questions are answered by an LLM agent that calls retrieval tools (search_cv, get_full_entry) over these CV records, rather than a static PDF resume.
- Backend: FastAPI serving a streaming chat endpoint, async PostgreSQL access via SQLAlchemy, Alembic-managed schema migrations, and per-hirer JWT access tokens scoped by expiry and query count.
- Frontend: Next.js/TypeScript chat UI with streamed responses, built with Tailwind CSS.
- Infrastructure: containerized with Docker Compose; Caddy handles TLS and reverse proxying in production.

## Engineering details
- **Security.** Per-hirer JWT access tokens, scoped by both expiry and a query
  count, with tokens stored hashed rather than in plain text. The system prompt
  is added server-side only and stripped from both the JSON and streaming
  responses, so it never reaches the client; a `system` message arriving in a
  request is dropped rather than forwarded to the model. Tool-call rounds are
  bounded so a misbehaving model cannot loop indefinitely.
- **Streaming.** Replies arrive token by token over server-sent events (SSE),
  parsed incrementally on the client and rendered as they land.
- **Asynchronous throughout.** Async FastAPI handlers, async SQLAlchemy against
  PostgreSQL, and async file access, so streaming a long reply does not block
  other requests. Concurrency is the normal case here, not an afterthought.
- **Shell scripting.** Bash underpins the operational side: the container
  entrypoint that applies Alembic migrations on start, and the backup scripts
  that dump the database and pull the private resources off the server.
- **Caching.** The tool schema and CV index are loaded once and shared across
  every conversation rather than re-read per request.

For the wider stack this sits in, see "Frameworks and Tools".

## Authorship
Michael built this application. It is one of his projects, not a third-party
product, a hosted service, or a template he filled in — he designed and wrote
it end to end, from the database schema through the frontend to the deployment
that is serving this conversation. If a hiring manager asks who made this chat
bot, the answer is Michael, and the thing they are using is itself a work
sample.

## Status
Live. This is the application serving this conversation — deployed and publicly reachable.

## Note
Designed and built end-to-end — backend API, database schema, frontend, and deployment setup — as a self-contained full-stack project, distinct from his day-to-day backend-focused work at iEDI.