# Custom Caddy build with the rate-limit module (not in the stock image),
# used to throttle /api/chat and /api/admin per client IP.
FROM caddy:2-builder-alpine AS builder

RUN xcaddy build --with github.com/mholt/caddy-ratelimit

FROM caddy:2-alpine

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
