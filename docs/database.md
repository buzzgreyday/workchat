# Database

Stop docker-compose to keep data and tables, the following will remove data and tables:
```bash
docker compose down -v
```

To build after development.
```bash
docker compose up --build
```

Use Alembic if docker container was taken down or schemas was changed:
```bash
docker compose exec backend alembic upgrade head
```

## Tables

| table | what it holds |
|---|---|
| `users` | One row per **company**, deduplicated on name. `users.name` is the company, not a person. |
| `tokens` | One row per issued access token: the person (`subject`), job title, quota and expiry. |
| `conversations` | One chat session, with `subject`/`company`/`job_title` snapshotted from the token. |
| `chat_messages` | Two rows per turn — the question as received, and the reply as it finished. |

`chat_messages.request_id` is 32 hex characters, W3C trace-id shaped. It ties the
user row and assistant row of one turn together, and is the column a future
OpenTelemetry `trace_id` drops straight into.

## Reading what hirers asked

Normally through the admin API (see `docs/deployment.md`). Directly, when the API
is down or for ad-hoc digging:

```bash
docker compose -f docker-compose.prod.yaml exec -T db \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
    SELECT c.created_at, c.subject, c.company, m.role, left(m.content, 80) AS content
    FROM chat_messages m
    JOIN conversations c ON c.id = m.conversation_id
    ORDER BY m.created_at DESC LIMIT 50;"'
```

## Retention and erasure

Message content is scrubbed after `CHAT_RETENTION_DAYS` (default 30) by
`scripts/purge-chat-content.sh`, run nightly from cron. It nulls `content` and
stamps `redacted_at`, keeping the row, its counts and its timings — `content_chars`
preserves the size signal after the text is gone.

To erase one conversation immediately, use `POST /admin/conversations/{id}/redact`.

**Deletion order matters.** Every foreign key here is `ondelete="RESTRICT"`, so
rows cannot be removed piecemeal and `DELETE FROM users` alone will fail. A full
subject-erasure request has to walk the chain:

```
chat_messages  ->  conversations  ->  tokens  ->  users
```

**Backups lag the purge.** `scripts/backup-db.sh` keeps 7 daily, 4 weekly and 6
monthly dumps, so redacted content survives in backups for up to ~6 months after
it is scrubbed from the database. The honest position is a written retention
statement covering backups and letting the rotation age it out, not per-dump
surgery.
