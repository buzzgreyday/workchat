---
title: AI CV Chat Application
type: project
tags: [python, fastapi, typescript, nextjs, react, postgresql, sqlalchemy, alembic, docker, full-stack, full-stack-developer, backend, frontend, rest-api, jwt, openai, tailwind, tool-calling, llm, software-engineer]
dates: "2026-"
summary: "This chat application itself — a full-stack AI-powered CV assistant (FastAPI/PostgreSQL backend, Next.js/TypeScript frontend, Dockerized) that lets hiring managers query Michael's CV through a tool-calling LLM agent instead of a static resume. LIVE: deployed and serving this conversation."
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

## Status
Live. This is the application serving this conversation — deployed and publicly reachable.

## Note
Designed and built end-to-end — backend API, database schema, frontend, and deployment setup — as a self-contained full-stack project, distinct from his day-to-day backend-focused work at iEDI.