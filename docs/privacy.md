# Privacy

What this application keeps about the people who use it, why, and for how long.
Written for the operator — the person answering a data-protection question —
and kept next to the code that does it, so the two can be checked against each
other.

## People with a link

A link is issued to a named person, so their name, company, job title and —
if given — email and phone are stored with the grant (`users`, `tokens`). Their
questions and the answers are stored per conversation (`chat_messages`), and the
text is scrubbed after `CHAT_RETENTION_DAYS`, 30 by default. The details are in
[database.md](database.md#retention-and-erasure), including how to erase one
person on request.

## Guest trials

When trials are on (`TRIAL_ENABLED`), a visitor with no link can ask a few
questions. To keep that from being abused, each trial is limited to one per
**IP address** per UTC day.

**What is stored:** in `trial_requests`, the day, the proof-of-work challenge
that paid for the trial, and `ip_hash` — an HMAC-SHA256 of the address under a
key derived from `TRIAL_SECRET` *and the date*. IPv6 addresses are cut to their
/64 first (a household's whole range is one visitor).

**What that hash can and cannot do:** it can answer "has this address already
had a trial today?" and nothing else.

- It is not the address and cannot be turned back into one: the key is secret,
  so the usual attack on hashed IPv4 addresses — hashing all four billion and
  comparing — needs a key nobody outside the server has.
- It cannot link a visitor across days. The key changes every day, so the same
  address hashes to something unrelated tomorrow, and yesterday's hashes match
  nothing.
- It is deleted when its day is over: every trial request first deletes the rows
  of earlier days (`SQLTrialRepository.reserve`), and
  `scripts/purge-trial-requests.sh` does the same just after midnight UTC, for
  days nobody asked (crontab in [deployment.md](deployment.md)).

**What is not stored:** the address itself, anywhere. It is not in the
database, and not in the application's logs — `ip`, `client_ip` and `ip_hash`
are on the log redaction list, and uvicorn's access log is off. Caddy's access
log masks addresses to their network (/16 for IPv4, /32 for IPv6). No third
party is involved: the bot check is a proof-of-work solved in the visitor's own
browser, with no captcha service and no tracking.

**The trial cookie.** After a trial, the browser is given `cv_trial` (the
name is configurable as `TRIAL_COOKIE_NAME`) for `TRIAL_COOKIE_DAYS`, 30 by
default. It holds the date of the trial and an HMAC signature of that date —
no identifier — and the server keeps no record of it. While a browser carries
a valid one, no new trial is offered. It is what keeps the per-day address
limit from handing the same browser a fresh trial every morning; clearing it
is possible, and the daily ceiling bounds what that is worth.

**The trial itself** is an ordinary grant with the subject "Guest": its
questions and answers are kept like anyone's, under the same 30-day scrub, and
attributed to no one.

**Lawful basis:** legitimate interest (GDPR art. 6(1)(f)) — preventing abuse of
a service that costs money per question. The data is the minimum that achieves
it, held for at most a day, and in a form that identifies no one. The visitor is
told before they start: the chat shows a one-line notice beside the button that
starts a trial.

## Cookies

Two, both set by the API's host, both httpOnly and SameSite=Strict, and
neither read by anything but the endpoints that set them:

- `cv_refresh`: the session. Keeps a conversation going across a reload, for
  as long as the grant lasts.
- `cv_trial`: set only after a guest trial, for 30 days. The trial's date and a
  signature, nothing else (see above).

Both are strictly necessary to a service the visitor asked for — a
conversation, and a trial on the terms it is offered on — which is the
ePrivacy exemption (art. 5(3)): no consent banner is needed. Neither is used
for analytics, advertising or anything else, and nothing is set for anyone
else. The notice beside the trial button says both things the trial keeps.

## Backups

`scripts/backup-db.sh` keeps dumps for up to about six months, so anything
deleted or scrubbed from the database lives on in backups until they age out.
That includes a day's trial hashes — which, by the time any backup could be
read, belong to a key that no longer exists.
