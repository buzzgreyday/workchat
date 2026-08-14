---
title: Software Developer @ iEDI
type: experience
tags: [backend, backend-developer, backend-engineer, software-developer, software-engineer, python, fastapi, pyramid, pydantic, pika, rabbitmq, message-queues, lxml, xml, pandas, mongodb, nosql, javascript, api-development, rest-api, erp, e-invoicing, databases, sql, ci-cd, github-actions, code-review, docker, kubernetes, rancher, nomad, testing, github, integrations, cron, monolith, microservices, distributed-systems, architecture, service-integration, refactoring, technical-debt, legacy-code, troubleshooting, production-support, solution-ownership, system-design]
dates: "September 2025 - present"
summary: "Software Developer / Backend Engineer at iEDI (Denmark, on-premise) - owns and troubleshoots production integrations and services (partner APIs, cron jobs, price-catalogue/invoice/despatch advice/document flows), makes independent design decisions, and helps shape team development practices. Daily stack is Python with FastAPI and Pyramid, Pydantic, Pika/RabbitMQ, lxml, Pandas, MongoDB and SQL, shipped via GitHub Actions and peer-reviewed pull requests onto Kubernetes (Rancher), now migrating to HashiCorp Nomad. ARCHITECTURE: not microservices — the main engine is a monolith, surrounded by a large set of customer-tailored RESTful APIs and services that the team is working to consolidate. IN PRODUCTION BUT INTERNAL: proprietary employer code, not publicly viewable or installable."
skill_notes:
  kubernetes: "Created and managed services, ingress, and deployments through Rancher; did not author raw manifests/Helm charts or design cluster architecture from scratch."
  rancher: "The cluster management UI through which he works with Kubernetes at iEDI."
  javascript: "A small part of the work at iEDI; his professional focus there is backend Python."
  microservices: "Not the architecture at iEDI, and not a claimed skill — the main engine is a monolith surrounded by customer-tailored services. Tagged so the question is answerable honestly rather than inferred."
  distributed-systems: "Many RESTful APIs deployed in Kubernetes and now migrating to Nomad, around a monolithic central engine. Some of those services use RabbitMQ; it is not the backbone of the estate."
  monolith: "iEDI's main engine is a monolith, surrounded by customer-tailored REST APIs the team is working to consolidate."
---

## Role
Software Developer, iEDI — Denmark, on-premise
**September 2025 - present**

## Status
Running in production at iEDI, but internal: this is proprietary employer code, so there is no public repository, package, or URL to point a hiring manager at.

## What I did
- Own and troubleshoot a number of distinct production integrations and services — partner API integrations, scheduled cron jobs, and services handling price catalogues, invoices, despatch advices, and other business documents.
- Make independent decisions on API/service design, and work with the team to streamline development practices and code structure.
- Designed and built REST APIs for exchanging high priority business documents, integrating with ERP systems and international e-invoicing.
- Fixed a number of critical design flaws — for example, despatch advices were sometimes not delivered, or delivered with erroneous content. The redesigned flow relies on the supplier's packing slip instead of warehouse picks, resulting in no errors, leaner code, and a simpler lifecycle.
- Worked across relational and non-relational databases — SQL and MongoDB.
- Wrote unit and integration tests, technical documentation, and performed GitHub peer-reviews.
- Built CI/CD pipelines with GitHub Actions.
- Deployed Docker services in Kubernetes, managed through Rancher.
- Migrated Kubernetes services to a new HashiCorp Nomad environment.

## Stack
Python throughout, with FastAPI and Pyramid for services and Pydantic for
validation. Pika for RabbitMQ message queues where services use them, lxml for the XML that
underpins the e-invoicing and business-document flows, and Pandas for data
handling. MongoDB alongside SQL. Some JavaScript, though the work here is
predominantly backend Python. CI/CD runs on GitHub Actions, with peer
review on every pull request.

## Architecture: a monolith, not microservices
The main engine is a monolith. Around it sits a large set of RESTful APIs and
services tailored to individual customers — so the estate is distributed in
practice, but it is not a microservice architecture, and he would not describe
it as one. Reducing the number of those customer-specific APIs is ongoing work —
that consolidation is about the bespoke API surface, not about decomposing the
monolith — as is the migration from Kubernetes to Nomad.

What that does mean in practice: working across many separately deployed
RESTful APIs and their integrations, orchestrated in Kubernetes and now moving
to Nomad, with some of those services using RabbitMQ for message queues —
without the service-per-bounded-context design, or the service mesh and
distributed-tracing tooling, that a microservices role would usually expect. His observability work with OpenTelemetry, Grafana, Loki
and Tempo was a self-initiated prototype aimed at exactly that gap (see
"Tracing and Distributed Logging").

For the full stack with depth noted per entry, see "Frameworks and Tools".

## Working with existing systems
Most of the work is on a codebase that predates him: reading unfamiliar code,
refactoring it, and reducing the technical debt it carries. The despatch
advice redesign above is the pattern — an existing flow diagnosed, then
rebuilt on the supplier's packing slip so it produced fewer errors and less
code than the legacy version it replaced. The API consolidation effort is the
same instinct at a larger scale.

Troubleshooting production failures is a routine part of the role. He does not
work an on-call rotation, and mentoring is not part of the job.