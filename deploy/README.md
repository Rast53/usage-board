# Autodeploy (repull) on a host

Moves a host such as **fornex-usa** to the image built from the newest `main`
merge with **no manual actions**. A systemd timer runs `autodeploy.sh`, which
repulls `ghcr.io/rast53/usage-board:latest`, recreates the app only when the
image changed, waits for health, and prints the running
`org.opencontainers.image.revision` label.

`pull_policy: always` on the `app` service means an ordinary
`docker compose up -d` repulls too — the timer just makes that automatic.

The repull contract is enforced in CI by the existing `test` job (`pytest -q` →
`tests/test_deploy_config.py`) and can be checked locally with the standalone
gate (it renders `docker compose config`):

```bash
deploy/check-pull-policy.sh                    # compose.app-only.yml
deploy/check-pull-policy.sh docker-compose.yml # needs a host .env
```

## Install (once, on the host)

The stack lives in a checkout, e.g. `/opt/usage-board`, with its secrets in
`/opt/usage-board/.env` (never committed):

```bash
sudo install -m 644 deploy/usage-board-autodeploy.service /etc/systemd/system/
sudo install -m 644 deploy/usage-board-autodeploy.timer   /etc/systemd/system/
# edit WorkingDirectory/COMPOSE_FILES in the unit if the path differs
sudo systemctl daemon-reload
sudo systemctl enable --now usage-board-autodeploy.timer
```

Observe:

```bash
systemctl list-timers usage-board-autodeploy.timer
journalctl -u usage-board-autodeploy.service -n 20 --no-pager
```

## Verify the running revision (acceptance)

```bash
docker inspect usage-board-app-1 \
  --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'
```

It must equal `git rev-parse main` of the `usage-board` repo after the CI image
for that merge is published. To make the script a hard gate, run it with the
expected commit:

```bash
EXPECT_REVISION="$(git -C /opt/usage-board rev-parse origin/main)" \
  /opt/usage-board/deploy/autodeploy.sh
```

## Manual one-shot

```bash
COMPOSE_FILES="-f compose.app-only.yml" deploy/autodeploy.sh
# bundled Caddy/TLS mode:
COMPOSE_FILES="-f docker-compose.yml" deploy/autodeploy.sh
```

The script only ever touches the image and the `app` container; it does not
read or modify `.env`.
