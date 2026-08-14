---
title: "Case: Migrating Kubernetes Services to Nomad"
type: case
tags: [migration, infrastructure, deployment, kubernetes, rancher, nomad, hashicorp, docker, containers, devops, ci-cd, solution-ownership, iedi]
summary: "Michael migrated iEDI's containerised services from Kubernetes, managed through Rancher, to a new HashiCorp Nomad environment, and the migration is still in progress across the estate. SCOPE: he created and managed services, ingress and deployments through the Rancher UI; he did not author raw manifests or Helm charts, and did not design cluster architecture from scratch. INTERNAL: proprietary employer infrastructure."
---

## The work
iEDI's services ran as Docker containers on Kubernetes, managed through Rancher.
Michael migrated services to a new HashiCorp Nomad environment; moving the rest
of the estate is ongoing.

## Scope, honestly
This is the caveat that matters most on this record, because "Kubernetes
migration" reads bigger than the work was:

- He created and managed services, ingress and deployments through Rancher, the
  cluster management UI.
- He did not author raw Kubernetes manifests or Helm charts.
- He did not design cluster architecture from scratch.

## Related
The observability gap in this estate — many separately deployed services without
distributed-tracing tooling — is what prompted his OpenTelemetry prototype (see
"Tracing and Distributed Logging").

## Status
In production at iEDI and still in progress, on internal infrastructure: nothing
here is publicly inspectable.