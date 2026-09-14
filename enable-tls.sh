#!/usr/bin/env bash
# usage-board: one-shot TLS activation (after the DNS A record exists).
# Run on fornex-usa: bash enable-tls.sh
# Idempotent-ish: safe to re-run (certbot webroot, nginx reload at the end).
set -euo pipefail

DOMAIN=usage.ohera.ru
UPSTREAM=127.0.0.1:8090
CONF=/etc/nginx/sites-available/${DOMAIN}.conf
LE_DIR=/etc/letsencrypt/live/${DOMAIN}

echo "1/4 DNS check: ${DOMAIN} → $(dig +short A ${DOMAIN} | head -1)"
if [ -z "$(dig +short A ${DOMAIN})" ]; then
    echo "   DNS record missing — add A ${DOMAIN} → this server IP first." >&2
    exit 1
fi

echo "2/4 ACME challenge (webroot)"
certbot certonly --webroot -w /var/www/letsencrypt -d ${DOMAIN} \
    --non-interactive --agree-tos --keep-until-expiring \
    --register-unsafely-without-email --deploy-hook "systemctl reload nginx"

if [ ! -f ${LE_DIR}/fullchain.pem ]; then
    echo "   certificate not issued" >&2
    exit 1
fi

echo "3/4 Enable 443 server block"
cp ${CONF} ${CONF}.http-only.bak
cat > ${CONF} <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        default_type text/plain;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${DOMAIN};

    ssl_certificate ${LE_DIR}/fullchain.pem;
    ssl_certificate_key ${LE_DIR}/privkey.pem;

    location / {
        proxy_pass http://${UPSTREAM};
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
EOF

echo "4/4 nginx reload"
nginx -t && systemctl reload nginx
echo "DONE: https://${DOMAIN} (cert renews via certbot.timer)"
