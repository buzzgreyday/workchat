---
title: Tracing and Distributed Logging
type: project
tags: [python, opentelemetry, docker, observability, backend, monitoring, software-engineer, grafana, loki, tempo, github]
dates: "2026"
summary: "Self-initiated backend project - prototyped OpenTelemetry tracing and distributed logging with Grafana, Loki and Tempo to demonstrate observability gains for iEDI's stack. PUBLIC BUT NOT HOSTED: source at github.com/buzzgreyday/grafana-observability, but it is a local prototype anyone can run themselves, not a deployed service."
---

## Technologies
Python, OpenTelemetry, Docker, Grafana, Loki, Tempo

## What it does
Prototyped OpenTelemetry tracing and distributed logging to demonstrate observability gains for iEDI's stack — showing how request tracing across services could improve debugging and monitoring of the document-exchange pipeline. Traces were exported to Tempo, logs aggregated with Loki, and both correlated and visualized in Grafana dashboards.

## Status
Public but not hosted. The source is open and publicly readable at
https://github.com/buzzgreyday/grafana-observability — the Docker-based OpenTelemetry, Grafana, Loki and Tempo setup anyone can clone and run locally. It is a demonstration prototype rather than a deployed service: there is no hosted instance to visit. Describe it as public code anyone can inspect and run themselves, not as running in production.
