---
title: "Case: Fixing and Simplifying the Despatch Advice Flow"
type: case
tags: [simplification, simplified, streamlining, redesign, refactoring, legacy-code, technical-debt, complexity-reduction, error-reduction, error-prone, reliability, bug-fixing, root-cause-analysis, problem-solving, troubleshooting, production-support, despatch-advice, business-documents, edi, e-invoicing, integrations, solution-ownership, system-design, iedi]
summary: "The clearest example of Michael simplifying something at iEDI. Despatch advices were sometimes not delivered at all, and sometimes delivered with erroneous content, because the flow was built on warehouse picks. He traced it to that choice of source data and rebuilt the flow around the supplier's packing slip instead: the errors stopped, the code got leaner, and the document lifecycle got simpler than the legacy version it replaced. A fix to an existing system, not a greenfield build. INTERNAL: proprietary employer code, so there is no public repository to point a hiring manager at."
---

## What a despatch advice is
The document a supplier sends a customer to say what has actually been
despatched — what is in the shipment, and on the way. Customers reconcile it
against what they ordered and against the invoice that follows, so a missing or
wrong one is not a cosmetic problem: it breaks the receiving end of the trade.

## What was wrong
Despatch advices coming out of the flow were unreliable in two different ways:

- Some were never delivered at all.
- Some were delivered carrying erroneous content.

Both are the kind of fault that surfaces as scattered individual complaints
rather than as one obvious outage, which is what makes them easy to keep
patching case by case.

## The root cause
The flow generated the document from warehouse picks. That was the design flaw:
picks describe the work of assembling an order, which is not the same thing as
what physically left the building, so the document was being derived from data
that could not reliably answer the question it existed to answer.

## What he changed
Rather than continue correcting individual failures, he rebuilt the flow around
the supplier's packing slip — the record of what was actually despatched.
Choosing the right source of truth removed the mismatch the old design depended
on.

## Outcome
- The delivery and content errors stopped.
- The implementation came out leaner than the one it replaced.
- The document lifecycle ended up simpler, so there is less to go wrong and less
  to understand next time someone works on it.

Fewer errors *and* less code, from the same change — the simplification was not
a trade against reliability, it was the same thing.

## Why this one is representative
Most of what he works on at iEDI predates him: reading unfamiliar code,
refactoring it, and reducing the technical debt it carries. This is that pattern
at its clearest — an existing flow diagnosed rather than patched, then rebuilt on
the right data so it produced fewer errors and less code than the legacy version.
The ongoing consolidation of customer-specific APIs is the same instinct at a
larger scale (see "Case: Consolidating Customer-Specific APIs").

It is also worth reading as evidence of scope: he owns and troubleshoots these
production integrations, and this was his call to make rather than a ticket handed
to him with the answer attached.

## Status
Running in production at iEDI, and internal: proprietary employer code, so there
is no public repository, package, or URL a hiring manager can inspect. For the
role this sits inside, see "Software Developer @ iEDI".