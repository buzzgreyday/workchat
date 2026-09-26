# Changelog

All notable changes to this project will be documented in this file.

_Versioning: this repo is versioned as a single unit — one tag per release,
covering both frontend and backend together. `backend/pyproject.toml` and
`frontend/package.json` version fields are bumped to match on release, not
tracked independently._

## [Unreleased]

### Added

- The embed takes fonts from the host: it inherits the page's font by
  default, and `--chat-font`, `--chat-font-weight`, `--chat-font-title`,
  `--chat-font-title-weight` and `--chat-font-title-size` choose otherwise.
  The host loads the faces; the element names them.
- `header="none"` hides the chat's header, for a host that frames it with its
  own. The allowance still arrives as `workchat-usage`.

### Changed

- The element's defaults are plain. chat.mringdal.com's palette, Nunito and
  Bebas moved to `src/app/theme.css`, which only the standalone site loads,
  so an embed no longer inherits one site's branding.
- The card's height cap follows the chat's own width (a container query), not
  the window's. A chat in a narrow dialog on a wide screen fills the dialog.
- The title is written in normal case. Bebas draws capitals regardless, and
  screen readers no longer spell it out.

### Fixed

- The embed's title was a 2.5rem system font at weight 400: the Bebas size
  and weight, without Bebas, which never reached the shadow root.

## [0.8.0] - 2026-09-26

### Added

- `<workchat-chat>`, the chat as a custom element any page can embed with a
  script tag. Built from the app's own components into `public/embed.js` and
  served at `/embed.js`, so a release here reaches every embedding page on its
  next load. Attributes `api-url`, `about`, `claim` and `owner-name`; a
  `workchat-usage` event; the `--chat-*` palette as its styling surface. See
  `frontend/EMBED.md`.
- `about` puts a question in the composer, unsent, for the visitor to read,
  edit or delete.
- `npm run test:contract` runs the site's Playwright suite against a freshly
  built bundle, so a change to the element's surface fails here first.

### Changed

- New type and palette: Nunito Light for text, Bebas Neue for the title, and a
  blue scheme. Only Nunito (OFL) is committed; Bebas comes from
  `next/font/google`, because the Fontshare copy's licence forbids a public
  repository.
- The GitHub and LinkedIn links moved out of the chat header onto the
  standalone page, below the card.
- The composer is 16px at every width, so a question is the same size typed
  as it is once sent. It was 14px on desktop.
- Your own messages take `--chat-text` like the rest of the text.

### Removed

- The embed's `owner-github` and `owner-linkedin` attributes, with the links
  they fed. A page still setting them gets nothing, and no error.

### Fixed

- `backend/uv.lock` carried 0.7.0 through 0.7.1 and 0.7.2.

## [0.7.2] - 2026-09-22

### Fixed

- The chat no longer slides up the screen on a phone while a reply streams in.
  Auto-scroll called `scrollIntoView()` on a sentinel at the end of the
  transcript, once per token. `scrollIntoView` is not scoped to the nearest
  scroller — it moves every scrollable ancestor it can, which on a phone
  includes the page itself while the keyboard is animating and `--app-height`
  is a frame behind it. It now sets `scrollTop` on the transcript, which can
  only ever move the transcript.
- Asking a question while scrolled up now brings the transcript back down, so
  the question and its answer no longer land below the fold.
- A reply that arrives in one large chunk is followed instead of stopping
  auto-scroll. Whether the reader is following is now remembered from their
  last scroll rather than measured after the new content has landed.
- The transcript stays on its newest line when the keyboard resizes it.
- Auto-scroll runs before paint, removing a one-frame jitter per token.

### Reverted

- The `min-h-0` added to `main` and the chat card in 0.7.1. It did not address
  the bug above; the transcript already carried the `min-h-0` that matters.

## [0.7.1] - 2026-09-21

### Fixed

- Resizing bug on mobile.

## [0.7.0] - 2026-09-21

### Fixed

- The Geist font now actually applies. It was declared as
  `--font-sans: var(--font-sans)` — a custom property referring to itself,
  which is a dependency cycle, so it computed to the guaranteed-invalid value.
  The rule that read it carried no fallback, and an invalid value on an
  inherited property means `inherit`; the root element has no parent, so it
  landed on whatever font the browser starts with. Geist was downloaded on
  every page load and thrown away, and the compiled stylesheet never once
  mentioned it. Geist Mono was being preloaded on top of that and no rule ever
  referred to it at all; it has been removed rather than fixed.

- The composer stays above the on-screen keyboard on iOS. The previous fix
  asked the browser to shorten the layout viewport when a keyboard opens, which
  Chromium honours and Safari ignores — Safari shrinks only the *visual*
  viewport and scrolls to reach the focused field, and since the document can
  no longer scroll there was nowhere for it to go. The height is now measured
  from the visual viewport, which is the one number both engines report
  honestly, and published as a custom property so a keyboard animation does not
  re-render the transcript sixty times a second. A pinch-zoom shrinks that
  measurement too, so zooming is excluded: matching it would crop the chat to
  whatever slice of the page was on screen.

- The chat no longer shows a band of white below itself on a phone. Three
  things were true at once and only together did they produce it: the shadcn
  `--background` token was pure white and `body` painted with it, the root
  element painted nothing at all — and the root is what the browser propagates
  to the viewport canvas, which is the surface an overscroll drags into view —
  and nothing declared a `color-scheme`, so the scrollbars, the caret and the
  fill behind a rubber-band were all drawn for a light page regardless. The two
  canvas tokens now point at the chat's own background, the root paints it, and
  `color-scheme: dark` covers the surfaces no background can reach.

- The keyboard no longer pushes the page somewhere it does not paint. There was
  no viewport declaration at all, so the layout viewport stayed a full screen
  tall when the keyboard opened; the composer ended up behind it and the browser
  scrolled the document to reach it. `interactive-widget=resizes-content` asks
  for the layout to shrink instead, so `dvh` keeps meaning what the layout
  assumes it means. Document scrolling is now impossible rather than merely
  unlikely, which is what makes the fix hold on a browser that ignores the hint.

- The composer no longer scrolls before anything has been typed. Its placeholder
  was long enough to wrap, and a placeholder is laid out inside the box, so a
  one-row `textarea` became two rows tall and scrollable while still empty. All
  three placeholders are now short enough to fit, and a test asserts it for each
  of them rather than for the one that was reported.

- The composer shrinks back after a multi-line question is sent. Its height was
  written from inside `onChange`, which is the one moment the value changes
  because someone typed — sending clears it through state with no keystroke
  behind it, so the box kept the height of the question that had just left it.
  It follows the value now, so every route to a new one resizes.

- The composer asks for 16px on a phone. Below that, iOS Safari zooms the page
  when the field takes focus and does not zoom back out, which leaves the layout
  offset behind the keyboard and looks exactly like the chat having broken.
  Desktop keeps the 14px it always had. The alternative — disabling zoom in the
  viewport meta — would have fixed it by taking pinch-zoom away from everyone.

- The card is no longer capped below a phone's viewport. A flat 700px maximum
  left a band of dead background above and below the chat on exactly the screens
  with least room to spare; the cap now applies from the `sm` breakpoint up.

### Changed

- The whole visual scheme lives in one place. Colour, type, spacing and radius
  were spread across sixty-odd unnamed utilities in six components, with three
  literal `white`s and one stray `bg-slate-400` outside the token system
  entirely, and three adjacent panels of one card carrying three different
  paddings that nobody could tell apart from drift. They are named by role now
  — `canvas`, `panel`, `ink`, `accent`, `title`, `body`, `gutter`, `control` —
  and a restyle is an edit to the top of one stylesheet.

- The send button renders its own colour. It used to be painted by a custom
  class layered over a Button that was simultaneously painting itself from the
  stock shadcn palette; the one that won was decided by CSS layer ordering
  rather than by anything written down, and the class was invisible to the
  merge step that is supposed to resolve exactly that. The palette the Button
  reads now *is* this app's palette, so the override is gone rather than
  refereed.

- The end-to-end suite drives `?claim=` links. Eighteen of its nineteen
  navigations used `?token=`, the v1 shape being retired because it carries the
  access token in the URL — so the coverage was aimed at the path that is going
  away while the one that stays had a single happy-path test. Four of
  `useSession`'s five statuses had no test at all; they do now, along with the
  token refresh, the rotation conflict that has to be retried, and the claim
  being stripped from the address bar.

- The `?token=` tests that remain say so. They are in `e2e/legacy.spec.ts`,
  every title prefixed `legacy:`, with a note to delete the file when the last
  of those links expires. One of them covers something no test ever has: a
  genuinely v1-shaped token. The suite's fake token has always carried v2
  claims, so the fallback that reads the grant from `jti` had never run.

- The frontend is split by what each piece knows. `useChat` was 462 lines and
  owned the copy, the error-to-copy mapping, the greeting, the transcript, the
  persistence, the allowance, the composer's state and the streaming all at
  once; it is 200 lines of orchestration now. What the app says to a person is
  in one file that imports nothing. The transcript is a reducer, so "what may
  happen to a message" is a list of seven things rather than four closures
  spread through a send path. The allowance, the stored conversation and the
  greeting each have a hook. None of this changes what the page does — the
  behaviour suite that guards it did not change either.

- The chat's parts read what they need instead of being handed it. Two contexts
  rather than one, deliberately: the transcript changes on every streamed token,
  and a single context would have re-rendered the header and the composer once
  per token for the length of every reply — worse than the prop-drilling it
  replaced.

- The service layer no longer imports from the hook layer. `AuthFetch` and
  `SessionStatus` were declared inside `useSession`, so two services and every
  pure module had to reach into a React hook to name them; they are types in
  `src/types/session.ts` now. The backend's URL was written out three times and
  is written once.

- Playwright runs a phone as well as a desktop. Every fault above is invisible
  at 1280px and obvious at 393px, and the existing suite passed throughout. The
  new project is a chromium device descriptor, so CI needs no second browser.

### Removed

- Around seventy dead custom properties, including a whole dark-mode palette
  that nothing could ever select — the variant it was written for is
  class-based and no element has ever carried the class. Darkness here comes
  from the palette itself and from `color-scheme`. The variant declaration
  stays: without it those `dark:` utilities would fall back to
  `prefers-color-scheme` and start applying on anyone's machine set to dark.

- Dead code: an empty `lib/jwt.ts`, five shadcn primitives nothing rendered, the
  five Next scaffolding SVGs in `public/`, a `getToken()` that read a credential
  from the URL the server has read since the owner work landed, and two
  dependencies — `@tanstack/react-query` and `motion` — that were installed and
  never imported.

## [0.6.0] - 2026-09-20

### Fixed

- A reply that fails mid-stream no longer leaves the page unusable. 0.4.0 added
  an error frame so a failure would be distinguishable from a dropped
  connection; the frontend logged it to the console and did nothing else. No
  terminal frame follows a failure, so the bubble stayed in its streaming state
  — and because the composer is shut while a reply streams, it stayed shut. The
  only way out was a reload, with nothing on screen saying why. The failure is
  now shown where the answer would have been, and the allowance is re-read,
  since the question was spent before the model was ever called.

- A reload keeps the conversation. The session already survived one — a
  single-use claim link would be a cruel thing to lose to F5 — but the
  transcript and the conversation id did not, so the agent lost every turn of
  context and the backend opened a second conversation row for the same person.
  Both are kept for the life of the tab now, keyed to the grant so a different
  link opened in the same tab starts clean. The access token is deliberately
  not kept: it lives in memory so that script on the page cannot read it, which
  is the whole reason the refresh half is an httpOnly cookie.

- Scrolling up to re-read an answer no longer drags you back down. The
  transcript followed every change to the message list, which during a streamed
  reply is every token, so the one moment you might want to look back was the
  one moment you could not. It follows only when you are already at the bottom.

### Changed

- The chat says it is opening a session instead of greeting nobody. A claim
  link costs a round trip before it knows who is reading, and that gap was
  filled with a bare "Hi! 👋" that then flipped to a name. It shows the same
  typing indicator every reply uses. A `?token=` link is the access token
  itself, so that hirer is still greeted immediately.

- The header and the browser tab name whoever the deployment belongs to, from
  `OWNER_NAME`, `OWNER_GITHUB_URL` and `OWNER_LINKEDIN_URL`. They had been
  hardcoded to the author — something 0.1.11 admitted and deferred — and the
  tab still read "Create Next App". Read on the server per request rather than
  through `NEXT_PUBLIC_`, which `next build` would freeze into the bundle: one
  image serves any owner, and changing a name is a restart. A variable set but
  empty means there is no such link and hides it; unset means use the default.

- The composer is a textarea. Enter still sends, Shift+Enter opens a second
  line, which a two-sentence question needs. Links in an answer open in a new
  tab rather than navigating away from the chat.

- Screen readers are told what is happening: the transcript is a log, the
  composer and the send button are labelled, and a hidden status line says when
  a reply is being generated. Deliberately not a live region around the reply —
  that reads a streamed answer out one token at a time.

### Added

- Playwright tests for the chat page, and CI runs them. This was the first
  frontend test in the project: the three fixes above are exactly the kind no
  type checker sees, and every one of them had been reasoned about rather than
  observed. Each test is named for what broke, and the two that matter most
  were checked by putting the bug back. The backend is mocked at the network
  boundary, so they need no database, no key and no stack.

- `docs/architecture.md` records what a request actually costs, measured rather
  than estimated — which statements each endpoint makes, why only one of them
  is a question a token claim could answer, and why the session read that
  remains is worth keeping.

## [0.5.0] - 2026-09-20

### Removed

- `python -m app.build_index` is gone, and so is `resources/index.json`. What
  remains of that script is `python -m app.build_skills`, which only regenerates
  the skills list inside `skills.md` — a tracked file, produced locally and
  committed like any other source. The server never runs it.

  Deployment lost two steps with it. There is no index to build after a release,
  and no `chown -R 1000:1000 backend/resources` to remember beforehand, because
  nothing in the container writes to that directory any more; in production it
  is now mounted read-only. Updating is `git pull` and `up -d --build`, which is
  what the deploy workflow already ran.

### Changed

- The CV index is built by the process that serves it. On startup the backend
  scans `backend/resources/`, parses the frontmatter of every markdown file and
  holds the corpus in memory. The records, their order and the ranking are
  unchanged — what is gone is the step between editing a CV file and the site
  knowing about it.

  Forgetting that step was the failure. The index was a gitignored artifact
  built by hand, and the deploy never built it, so a release that changed any CV
  record left the site answering from the previous one — with `/health` passing
  throughout, so nothing surfaced the staleness. The index was never expensive
  enough to be worth an artifact: twenty files and about 46 KB of markdown, with
  no embeddings and no API calls behind it, read in milliseconds.

  A record that will not parse is skipped with its name in the log rather than
  taking the other nineteen with it. A resources directory that yields nothing
  at all stops the server before it binds a port, so the container never reports
  healthy and a deploy that shipped a broken mount fails instead of going live
  with nothing to answer from.

  The markdown is read in the same pass that parses the frontmatter, so the
  first search of a running server touches no disk, and a record nobody can read
  surfaces at boot rather than on the one question that needed it.

  Editing a record on a running server still needs a restart — the corpus is
  read once. In development that is automatic: the resources directory is
  watched, so a saved edit reloads the app and rebuilds the index.

- Decoding a token produces typed claims rather than a bare dict. `decode()`
  returned `dict`, so the type of every v2 claim was `Any` through the paths
  that decide who may spend a hirer's quota. The claims are their own model now,
  deliberately not the one used to mint tokens: that one defaults `max_queries`
  to 20, which would invent a quota for a token carrying none, and types `typ`
  as a literal, which would turn an unrecognised token type into a parse failure
  where the service wants to answer "not an access token".

  Nothing about a v1 token's shape is tightened — every field is optional, and
  those links are in inboxes and on printed QR codes. A `ver` that is a boolean,
  a string or a float is now refused rather than read as version 1; no token
  this service signs carries one, and both answers were already 401.

- The admin write endpoints return response models instead of hand-built JSON,
  so their output is validated and the ids are serialised rather than converted
  by hand. Issuing a token still builds its own response, because it is the one
  endpoint that answers in two media types.

- Configuration is an object built on demand rather than a page of module
  constants read at import. `app/common/config.py` no longer exports anything
  environment-derived: `SECRET_KEY` is `get_settings().secret_key`, and a fork
  carrying local patches against those names will need the same edit. Values
  that consult no environment — the signing algorithm, the tool-round cap, the
  cookie path — stay constants, because they are facts about the application
  rather than settings.

  Importing this application used to require a fully configured environment.
  Seven secrets were read at module level, the system prompt was loaded from
  disk, the database engine was opened, a `FastAPI` was constructed, and `Auth`
  read the signing key when the class was defined — all before anyone had asked
  for a server. The test suite paid for it in the only currency available: seven
  environment variables set above its own imports, and a `# noqa` on every
  import below them. An application is built by `create_app()` now, and
  `app/main.py` calls it, which is the moment a missing secret should stop
  everything.

  Logging is the deliberate exception and still reads `DEV_MODE` directly:
  handlers have to exist before anything logs, and a misconfiguration that could
  not be logged would be the wrong trade.

- Services take their collaborators instead of reaching for them. `CVSearch`
  takes the directory it reads, `Auth` takes its notifier, and `Auth`'s methods
  take plain arguments — the three dependency functions that wire them to a
  request live at the bottom of that module, the same service-and-adapter split
  the chat service already keeps. Nothing about what the application does
  changes; what changes is that overriding any of it in a test is now the
  mechanism FastAPI already provides rather than reaching into a module.

### Fixed

- A hirer's contact details and a grant's `token_hash` no longer reach the log.
  Issuing one token wrote the email and phone five times and the hash once, all
  at INFO and so all of it in production — while the same codebase keeps chat
  message text behind a flag at debug, because logging that was judged
  unacceptable. Contact details were held to no standard at all.

  The hash is the worse half: it is what a bearer is authenticated against, so a
  log holding it holds the verifier for every token on the grant. The issue path
  logs identifiers now — `token_id`, `user_id`, `company` — and a redaction
  filter on the log handler drops a deny-list of field names wherever they
  appear, including nested inside a record-shaped payload. The call sites are
  already written not to pass them; the filter is what stops the next one, since
  a log is the only store here with no retention policy and no redaction path.

- SQL echo is its own opt-in rather than following `DEV_MODE`. It writes every
  statement and its bound parameters to the log, which on the issue path meant
  the same email, phone and hash again — in the message rather than the
  structured fields, where the redaction filter cannot reach them. Every local
  session was doing it by default. `SQL_ECHO=1` turns it back on for debugging a
  query.

- `RESOURCES_DIR` and `SYSTEM_PROMPT_PATH` can be set in `backend/.env`. Both
  were computed *above* the `load_dotenv()` call, so neither had ever been
  readable from that file — only from the real environment, which is not where
  the documentation says configuration lives.

## [0.4.0] - 2026-09-19

### Removed

- `POST /chat` is gone; chat is streaming-only. Nothing in the browser used it —
  the client has always called `/chat/stream` — and keeping a second endpoint
  meant keeping a second implementation of the same tool-calling loop, which is
  where the duplication this release removes came from. The eval harness now
  reads the stream, and the dead `send()` path went with it.

### Changed

- The chat service is a pipeline of generators rather than a class. A turn
  yields domain events; a recorder passes them through and writes the
  transcript; the route encodes them as SSE frames. Nothing in the service
  mentions SSE and nothing in the route mentions OpenAI — which is what makes
  one loop enough where there were two.

  Everything a turn accumulates now lives in generator locals, so a second turn
  cannot inherit the first one's reply or tool counts. The previous class kept
  them on the instance and relied on a fresh one being built per request.

- Searching the CV no longer imports the OpenAI SDK. What the model is shown and
  told about the results — the schemas, the JSON encoding, the prose steering it
  toward opening an entry rather than answering from a summary — moved to an
  adapter beside the chat service. The index and the markdown it reads are now
  cached rather than re-read on every search.

### Fixed

- A reply that fails mid-stream now says so. The client receives an error frame
  instead of a stream that simply stops, which was indistinguishable from a
  dropped connection; the reason is logged server-side rather than shown.

- An empty assistant message is no longer stored and echoed back, so a turn that
  produced no text stops appearing as a blank entry in the next question's
  history.

- A tool call the service cannot run is dropped rather than assembled. The
  non-streaming path filtered these and warned; the streaming path never looked,
  and there is only one path now.

## [0.3.0] - 2026-09-19

### Changed

- Persistence moved behind a repository layer. `app/services/db.py` — which had
  grown to hold every query in the app — is gone, replaced by
  `app/repositories/`: a contract stated in domain terms, and an `sql/` package
  that is the only place naming SQLAlchemy. `AsyncSession` now appears in two
  files rather than nine, and no ORM row crosses into a route or a service.

  There is deliberately no unit of work and no `commit` in any abstraction. A
  SQLAlchemy `Session` is already one, and a store without transactions could
  only stub a `commit` while implying a guarantee it cannot keep. Instead the
  request owns its transaction and repositories flush — except for a named few
  that are durable on return, because a spend a later failure could undo is a
  free question.

- The chat model is configurable per environment. Development defaults to
  gpt-4.1-nano, where the question is whether the tool round-trip works rather
  than whether the answer is good; production still gets gpt-4.1-mini, which
  measurably answers depth questions better. `OPENAI_MODEL` overrides either.

### Fixed

- Conversation message counts no longer lose turns. The count was incremented in
  Python against a stale read, so two turns arriving together both wrote the same
  value and one was lost — five concurrent questions recorded two. The database
  computes the increment now.

- Listing conversations stopped issuing a query per row. A page of fifty cost a
  hundred and one round trips, all to fetch two truncated preview strings; it is
  one windowed query now.

- Refreshing a token can no longer fail while notifying the operator. Replay
  detection rolled back a session whose rows the caller still held, so reading
  the grant's owner afterwards risked lazy IO outside the async context; the
  caller now holds a plain value that no rollback can expire.

## [0.1.13] - 2026-08-14

### Changed

- The agent runs on gpt-4.1-mini. Retrieval had stopped being the limiting
  factor: over 26 questions x 3 runs the previous model scored 22-24 against
  mini's 25-26, and its remaining failures were all cases where it fetched the
  right record and could not pull the fact out of it. It also never once worked
  out how long a role has run — "how long has he been at iEDI" got "since
  September 2025" in every arm ever measured — where mini answers it. Costs
  about a second more per reply.

### Fixed

- Asked to elaborate, the agent reads the record instead of paraphrasing its
  summary. Search results now say which records carried every word of the query
  and ask for those to be opened, and say plainly that "tell me more", "why" and
  "elaborate" cannot be answered from a summary. Questions whose answers appear
  only in a record body went from 2 of 6 to 6 of 6, and the agent now opens a
  record for 22 of 26 questions rather than roughly 1 in 20 — while still not
  bothering when nothing matched.

- A record is found whatever the case of its filename. The model retypes the
  name out of the search result and sometimes alters it — asking for "iEDI.md"
  when the file is "iedi.md" — which returned "no such file" and, being
  indistinguishable from the record not existing, sent it back to the summary.

### Added

- Eval probes for depth: six questions whose answers exist only inside a record
  body, since every earlier question could be answered from a summary and so
  could not measure whether the agent ever opens anything.

## [0.1.12] - 2026-08-14

### Fixed

- The agent no longer denies things the CV plainly contains. Asked whether
  Michael had ever simplified despatch advices, it replied that there was no
  record — while iedi.md describes the redesign outright. Two causes, both now
  addressed: search results were unranked, so the record matching every word of
  a query sat among records that merely share one common word; and the cases
  themselves lived inside large role records whose summaries could not represent
  them. Measured over 20 questions x 3 runs, wrong answers fell from 6-7 to 1.

- Search results are ordered best-first, each carrying how much of the query it
  matched. Unranked, an eleven-record result read as noise and the agent
  answered from whichever summary came first.

- Common words no longer decide a result. Matching is OR'd and substring-based,
  so "at" on its own matched every record in the CV — it sits inside
  "integrations" — and a question like "despatch advices at iEDI" came back
  claiming the whole CV was relevant.

- A hiring manager gets an answer when the tool-call budget runs out. Exhausting
  MAX_TOOL_ROUNDS ended the turn on whatever had been streamed, which for a model
  still asking for tools is nothing at all: an empty reply. One further call with
  tools disabled now yields a thinner answer built from what was already fetched.

### Added

- Per-case CV records, so a case has a summary that describes it rather than
  being buried in a role: the despatch advice redesign, the customer API
  consolidation, and the Kubernetes to Nomad migration.

- backend/evals: a 20-question harness that scores the agent on wrong denials,
  invented answers and missed facts, and attributes every failure to the
  retrieval step that caused it. It is what these numbers come from, and it
  re-scores saved runs when the scoring changes, so past results stay comparable.

## [0.1.11] - 2026-08-14

### Fixed

- No gender is hardcoded in application code (frontend has my name harcoded though). 
  The frontend however needs some additional tweeks, so we're saving this for later.
  This was more work than expected, but this is a good place to leave it for now and iterate.

## [0.1.10] - 2026-08-14

### Fixed

- The agent knows what day it is. It was reasoning from its training cutoff,
  telling hirers "today is in early 2025" and miscalculating how long Michael
  has been at iEDI.

## [0.1.9] - 2026-08-14

### Added

- The conversation list now shows the agent's latest reply beside the question,
  so a wrong answer is visible without opening each conversation.

### Removed

- The "questions are stored" notice in the chat UI.

## [0.1.8] - 2026-08-14

### Fixed

- The agent no longer opens with a claim of microservices experience before
  correcting itself; the tag that suggested it is gone, and the record is still
  found by search.

## [0.1.7] - 2026-08-14

### Added

- Chat turns are now stored, so it is possible to see what hirers actually asked
  and what the agent answered. Readable via `GET /admin/conversations`, content
  scrubbed after 30 days.

### Changed

- Logs are structured JSON and carry a request id. `extra={...}` fields were
  previously discarded by the format string; message content stays out of logs
  and lives only in the database.

### Fixed

- `search_cv` reports when nothing matched instead of returning the whole CV,
  which the model could not tell apart from a precise hit and answered from by
  inference.
- The iEDI record now states its architecture — a monolith surrounded by
  customer-tailored APIs — and describes RabbitMQ's actual, partial role.

## [0.1.6] - 2026-08-14

### Changed

- CV records now carry the vocabulary a hiring manager would actually search
  for, and the orphaned records are reachable by link.

## [0.1.5] - 2026-08-14

### Added

- A Frameworks and Tools record, and the real iEDI stack on the experience
  record it was missing from.

## [0.1.4] - 2026-08-14

### Fixed

- Long unbroken text no longer overflows the message bubble.

## [0.1.3] - 2026-08-14

### Fixed

- The chat window is no longer overlapped by the mobile browser's URL bar.

## [0.1.1] - 2026-08-12

### Security

- The system prompt is now added backend-side only and stripped from both the
  JSON and streaming chat responses, so it is no longer part of the history
  returned to clients. A `system` message present in an incoming request is
  dropped rather than forwarded to the model.
- The non-streaming chat path now bounds tool-call rounds with
  `MAX_TOOL_ROUNDS`, shared with the streaming path, instead of looping without
  an upper limit.

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
