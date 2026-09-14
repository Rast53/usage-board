# usage-board

Self-hosted dashboard for **AI coding subscriptions**: one screen with live
credits, quotas and rate-limit windows for your API plans — no vendor lock-in,
no telemetry, your keys never leave your server.

Supported providers (a card appears only for the keys you provide):

| Provider | Card shows |
|---|---|
| Z.AI GLM Coding | 5-hour + weekly + MCP quotas |
| Command Code GOAT | monthly credits + 5h / weekly windows |
| Kimi Coding | weekly quota + 5h window |
| OpenCode Go | monthly remaining + 5h / weekly windows |
| DeepSeek | balance + 24h/7d spend |
| OpenRouter | credits, key usage, per-model table |

Card UI (not a table), human language, mobile-friendly, vanilla JS — no
external JS libraries, no CDN dependencies. Auto-refresh every 30 s.

![screenshot](docs/screenshot.png)

## Quick start (Docker + automatic HTTPS)

You need: a Linux server with Docker (Compose v2.24+), a **domain** pointing
at it (A record → server IP), ports 80/443 free.

```bash
git clone https://github.com/Rast53/usage-board.git && cd usage-board
cp .env.example .env
# edit .env: DOMAIN, BASIC_AUTH_USER/PASSWORD, provider keys
docker compose up -d
```

Open `https://your.domain` → dashboard. Caddy obtains and renews a Let's
Encrypt certificate automatically.

**No domain yet?** Free options:

- [DuckDNS](https://www.duckdns.org) — free `something.duckdns.org`, takes 2
  minutes, works with Let's Encrypt (each subdomain is its own rate-limit unit).
- `sslip.io` / `nip.io` — zero registration: `<ip>.sslip.io` resolves to `<ip>`
  (e.g. `usage.203-0-113-10.sslip.io`). Fine for HTTP tests, **not** for Let's
  Encrypt (shared rate limits) — use for quick look only.

**Ports 80/443 already occupied** (existing nginx, etc.)? See
[Behind your own reverse proxy](#behind-your-own-reverse-proxy).

## Without Docker

```bash
pip install fastapi "uvicorn[standard]" PySocks
export DEEPSEEK_API_KEY=... USAGE_STATIC_DIR=./static
uvicorn app:app --host 127.0.0.1 --port 3210
```

Keys can also be passed as environment variables; see `.env.example` for the
full list (per-provider proxies, `SITE_TITLE`, `DISPLAY_TZ`, poll intervals).

## Behind your own reverse proxy

If something already terminates TLS on this host, run the app only and proxy
to it from your nginx/Caddy/Traefik:

```bash
docker compose -f docker-compose.yml -f docker-compose.app-only.yml up -d
# app now listens on host port 8080 (APP_PORT in .env)
```

Keep `BASIC_AUTH_*` set unless your proxy already authenticates.

Minimal nginx server block (with your own cert):

```nginx
server {
    listen 443 ssl;
    server_name usage.example.com;
    ssl_certificate     /etc/letsencrypt/live/usage.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/usage.example.com/privkey.pem;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
    }
}
```

## Image

Prebuilt image on GHCR — no local build needed:

```bash
docker compose pull && docker compose up -d
```

`docker compose up -d --build` builds from source instead (offline-friendly).

## Security notes

- Provider keys live in `.env` on your server; the dashboard polls provider
  APIs read-only (balance/quota/usage endpoints).
- Set `BASIC_AUTH_USER`/`BASIC_AUTH_PASSWORD` whenever the dashboard is
  reachable from the internet — otherwise anyone can see your spend.
- UI is Russian-first (English UI is a possible contribution).

## API

- `GET /api/health` — status
- `GET /api/summary` — wallets + errors + site settings
- `GET /api/providers` — provider metadata
- `GET /api/wallets` — all enabled providers
- `GET /api/quota` — cached quota probes
- `GET /api/pace` — quota pace vs calendar
- `POST /api/refresh` — force a refresh

All routes are protected by basic auth when configured.

## Development

Single-file FastAPI app (`app.py`) + single-file UI (`static/index.html`).
Python 3.12. Run without keys: cards are simply hidden, the skeleton works.

## License

MIT
