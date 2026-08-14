---
title: Frameworks and Tools
type: frameworks
tags: [fastapi, pyramid, pydantic, pika, rabbitmq, amqp, lxml, xml, pandas, sqlalchemy, alembic, pytest, celery, redis, mongodb, sql, postgresql, nextjs, react, typescript, javascript, tailwind, shadcn, tanstack-query, opentelemetry, grafana, loki, tempo, docker, docker-compose, caddy, kubernetes, rancher, nomad, github-actions, ci-cd, code-review, dotnet, monolith, rest-api, frameworks, tooling, stack]
summary: "The frameworks, libraries and tooling Michael actually works in, grouped by area, with depth stated per entry. At iEDI his daily stack is Python with FastAPI and Pyramid, Pydantic, Pika/RabbitMQ messaging, lxml, Pandas, MongoDB and SQL, tested and shipped through GitHub Actions and peer-reviewed pull requests, deployed on Kubernetes via Rancher and currently being migrated to HashiCorp Nomad. Outside work he builds with PostgreSQL, SQLAlchemy, Redis, Celery, OpenTelemetry, Next.js, Tailwind CSS and .NET."
---

## How to read this
Depth is stated per entry rather than left to inference. "Built with" means
he has designed and shipped something in it; "worked in" means regular
production use inside an existing codebase; "used" means real but narrower
exposure.

## Backend frameworks
- **FastAPI** — built with, and worked in. Part of his regular stack at
  iEDI, and the backend of this chat application: streaming SSE endpoints,
  dependency-injected auth, and an LLM tool-calling loop.
- **Pyramid** — worked in, regularly at iEDI.
- **Pydantic** — worked in at iEDI, and built with here for request/response
  models and settings.
- **.NET (C#)** — used, outside work. A small REST API written deliberately
  outside his primary stack; a learning exercise, never deployed (see ".NET
  API").

## Data
- **MongoDB** — worked in, regularly at iEDI.
- **SQL and relational databases** — worked in, regularly at iEDI, across
  production integrations and document flows (see "Software Developer @
  iEDI").
- **PostgreSQL** — built with, outside work; the backing store for this
  application.
- **SQLAlchemy (async, 2.x)** — built with, outside work, as the ORM layer
  over PostgreSQL here.
- **Alembic** — built with. Schema migrations, applied automatically on
  container start in production.
- **Redis** — built with, outside work; touched only lightly at iEDI.

## Messaging and data processing
- **Pika (AMQP/RabbitMQ)** — worked in, regularly at iEDI, for message-queue
  work.
- **Celery** — built with, outside work, for task queues.
- **Pandas** — worked in, regularly at iEDI.
- **lxml** — worked in, regularly at iEDI, for XML processing — which sits
  close to the e-invoicing and document flows that make up much of the work.

## Frontend
- **Next.js (App Router)** — built with, outside work. The chat UI: server
  components plus client components for the streaming conversation.
- **React** and **TypeScript** — built with, alongside Next.js.
- **Tailwind CSS** — built with, outside work.
- **shadcn/ui**, **TanStack Query** — used, in this application's frontend.
- **JavaScript** — worked in, though only a small part of the work at iEDI;
  his professional focus there is backend Python.

## Observability
- **OpenTelemetry** — built with, outside work. Instrumented tracing and
  distributed logging in a self-initiated prototype.
- **Grafana, Loki, Tempo** — built with, in the same prototype, to
  demonstrate the observability gains for iEDI's stack (see "Tracing and
  Distributed Logging").

## Infrastructure and deployment
- **Kubernetes, managed through Rancher** — worked in. Services at iEDI are
  deployed on Kubernetes via Rancher; his work is through Rancher rather
  than authoring raw manifests or designing cluster architecture.
- **HashiCorp Nomad** — worked in, and current. iEDI is actively migrating
  services from Kubernetes to Nomad, and he is part of that work.
- **GitHub Actions** — worked in, regularly at iEDI, for CI/CD.
- **Docker and Docker Compose** — built with, and worked in. This
  application is fully containerized; Docker is also part of the day-to-day
  at iEDI.
- **Caddy** — built with. Reverse proxy and automatic HTTPS in production.

## Practice
- **Testing** — writing tests is a regular part of the work at iEDI, and the
  backend here has a pytest/pytest-asyncio suite running async tests against
  SQLite.
- **Pull request reviews** — peer review is part of the normal development
  flow at iEDI, not an occasional exercise.

## What the stack looks like in practice
iEDI's main engine is a monolith. Around it sits a large set of RESTful APIs
tailored to individual customers, which the team is currently working to
consolidate — so a meaningful part of the work is reducing bespoke surface
area rather than adding to it, alongside the ongoing Kubernetes-to-Nomad
migration.

## Scope of this list
This covers frameworks and tooling he has actually put to work, not
everything he has read about. Where his exposure is partial it says so, in
keeping with his general preference for stating the boundary of what he has
done rather than letting an impression stand (see "Development Philosophy").
