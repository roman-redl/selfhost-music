# Stock Caddy + the forwardproxy plugin (HTTP CONNECT proxy served from :443,
# see config/Caddyfile). Built on the VPS itself: `docker compose build caddy`
#(ARM64, a few minutes, cached after the first run).
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/caddyserver/forwardproxy

FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
