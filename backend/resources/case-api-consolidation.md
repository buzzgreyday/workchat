---
title: "Case: Consolidating Customer-Specific APIs"
type: case
tags: [simplification, streamlining, consolidation, complexity-reduction, refactoring, technical-debt, legacy-code, architecture, system-design, rest-api, api-development, monolith, distributed-systems, solution-ownership, iedi]
summary: "Ongoing team work at iEDI to reduce complexity in the service estate: a large set of customer-tailored REST APIs sits around a monolithic engine, and the team is working to consolidate them into fewer services. Michael is part of that effort. SCOPE: this is about the bespoke API surface, not about decomposing the monolith, and it is team work rather than his own initiative. IN PROGRESS and INTERNAL."
---

## The problem
iEDI's main engine is a monolith, surrounded by a large set of RESTful APIs and
services tailored to individual customers. The estate is distributed in practice
without being a microservice architecture, and the per-customer API surface is
larger than it needs to be.

## What is changing
The team is working to reduce the number of those customer-specific APIs by
consolidating them. Michael works across the affected services and is part of
that effort.

## Scope, honestly
Two caveats a hiring manager should have:

- The consolidation targets the bespoke API surface. It is not an effort to
  decompose or replace the monolith, and he would not describe it that way.
- This is team work in progress, not a finished result he owns end to end. The
  despatch advice redesign (see "Case: Simplifying the Despatch Advice Flow") is
  the one he drove himself.

## Status
Ongoing at iEDI, and internal: proprietary employer code, with no public
repository to point at.