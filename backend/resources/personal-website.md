---
title: Personal Website (mringdal.com)
type: project
tags: [nextjs, react, typescript, css, mdx, web-components, playwright, e2e-testing, github-actions, ci-cd, docker, caddy, frontend, full-stack, software-architecture, api-contracts, accessibility, performance, software-engineer, software-developer]
dates: "2026-"
summary: "Michael's personal website, mringdal.com — a Next.js/TypeScript site that hosts this chat as a separately deployed web component. Shows deliberate architecture: two independent repos joined only by a documented contract, contract tests against a stand-in and the real bundle, plain CSS, and gated automatic deploys. BUILT BY MICHAEL. LIVE at mringdal.com; source is private."
---

## Technologies
Next.js 16, React, TypeScript, plain CSS, MDX, Playwright, GitHub Actions, Docker, Caddy.

## Architectural decisions
- **Two independent systems.** The chat is not a dependency of the site. It is
  its own deployment, served as a `<workchat-chat>` web component and loaded at
  runtime, so either side ships without rebuilding the other. The site's whole
  knowledge of the chat is one URL.
- **A written contract instead of a version.** The element's attributes, its
  event and its CSS variables are documented as a public API. The site keeps a
  typed copy of that contract, and its end-to-end tests run both against a
  stand-in that implements exactly the contract and against the real bundle.
  The chat's own CI runs the site's tests too, so drift is caught on either side.
- **Theming through the contract.** The site styles the chat only through
  `--chat-*` CSS custom properties set on the host element. No code passes
  between the two.
- **Same site, on purpose.** Everything lives under mringdal.com, so the chat's
  session cookie can stay `SameSite=Lax` instead of becoming a third-party
  cookie that browsers block.
- **Resilience.** The chat runs inside an error boundary, and the site falls back
  to a plain link if the script never loads. The chat's ~130 kB bundle loads
  only for visitors who open it.

## Engineering choices
- **Plain CSS over a framework.** He moved the site and the chat off Tailwind
  to one stylesheet per concern with shared design tokens. Components only name
  their parts, and the visitor's stylesheet shrank from 27 kB to 19 kB.
- **Accessibility.** Larger reading text, animations that hold still under
  reduced motion, and focus handled deliberately when the chat window opens.
- **Tested as shipped.** The Playwright tests run against the production build,
  not a dev server, because that is the bundle a visitor receives.
- **Safe delivery.** Deploys run only after CI passes on `main`, one at a time
  and never cancelled midway. The workflow checks where a run came from before
  it uses secrets.
- **Small, readable history.** Work happens on short feature branches with
  conventional commits and a changelog written from the visitor's point of
  view. Every release is tagged.

## Status
Live at mringdal.com. The source repository is private.
