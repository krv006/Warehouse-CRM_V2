#!/bin/bash
# Ombor CRM — serverga bitta komanda bilan o'rnatish (Docker).
#
#   cd /var/www/ombor-crm && sudo bash deploy/server-setup.sh
#
# Nima qiladi:
#   1. Docker yo'q bo'lsa o'rnatadi
#   2. .env bo'lmasa yaratadi; SECRET_KEY, WEB_PORT, CADDY_NETWORK ni to'ldiradi
#   3. Konteynerni yig'ib ishga tushiradi (port bandligini tekshirib)
#   4. Reverse proxy: Caddy bo'lsa Caddy, bo'lmasa nginx
#   5. Kunlik eslatmalar uchun cron
set -e

DOMAIN=ombor.thesofmebel.uz
APP_DIR=/var/www/ombor-crm
DEFAULT_PORT=8089

cd "$APP_DIR"

# ------------------------------------------------------------------ 1. Docker
echo "==> 1/5 Docker"
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi

# Serverda Caddy ishlayaptimi?
CADDY=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -i caddy | head -1 || true)

# -------------------------------------------------------------------- 2. .env
echo "==> 2/5 .env"
if [ ! -f .env ]; then
    cp .env.example .env
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env
    echo "    .env yaratildi, SECRET_KEY qo'yildi"
fi

grep -q '^WEB_PORT=' .env || { echo "WEB_PORT=$DEFAULT_PORT" >> .env; echo "    WEB_PORT=$DEFAULT_PORT qo'shildi"; }

WEB_PORT=$(grep '^WEB_PORT=' .env | cut -d= -f2 | tr -d '[:space:]')
WEB_PORT=${WEB_PORT:-$DEFAULT_PORT}

COMPOSE="docker compose"
if [ -n "$CADDY" ]; then
    CADDY_NET=$(docker inspect "$CADDY" --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' | awk '{print $1}')
    if ! grep -q '^CADDY_NETWORK=' .env; then
        echo "CADDY_NETWORK=$CADDY_NET" >> .env
        echo "    CADDY_NETWORK=$CADDY_NET qo'shildi"
    fi
    COMPOSE="docker compose -f docker-compose.yml -f docker-compose.caddy.yml"
    echo "    reverse proxy: Caddy ($CADDY)"
fi
echo "    port: 127.0.0.1:$WEB_PORT"

# --------------------------------------------------------------- 3. Konteyner
echo "==> 3/5 Konteyner"
if ss -ltn 2>/dev/null | grep -q ":$WEB_PORT "; then
    if docker ps --format '{{.Names}}' | grep -q '^ombor-crm$'; then
        echo "    portni o'z konteynerimiz ushlab turibdi — qayta ishga tushiriladi"
        $COMPOSE down
    else
        echo
        echo "XATO: $WEB_PORT porti band (boshqa dastur ishlatyapti)."
        echo "      .env dagi WEB_PORT ni bo'sh portga o'zgartiring, masalan:"
        echo "      sed -i 's|^WEB_PORT=.*|WEB_PORT=8090|' $APP_DIR/.env"
        exit 1
    fi
fi

mkdir -p data media staticfiles
$COMPOSE up -d --build

# Reverse proxy'ga o'tishdan oldin ilova javob berishini kutamiz
printf '    ilova javob berishini kutamiz'
READY=0
for _ in $(seq 1 30); do
    if curl -fsS -o /dev/null "http://127.0.0.1:$WEB_PORT/api/docs/" 2>/dev/null; then
        READY=1
        break
    fi
    printf '.'
    sleep 1
done
echo
if [ "$READY" = "1" ]; then
    echo "    ilova tayyor: 127.0.0.1:$WEB_PORT"
else
    echo "    OGOHLANTIRISH: ilova javob bermadi — docker compose logs -f web"
fi

# ------------------------------------------------------------ 4. Reverse proxy
echo "==> 4/5 Reverse proxy"
if [ -n "$CADDY" ]; then
    CADDYFILE=$(docker inspect "$CADDY" \
        --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}')

    if [ -n "$CADDYFILE" ] && [ -f "$CADDYFILE" ]; then
        if grep -q "^$DOMAIN" "$CADDYFILE"; then
            echo "    $DOMAIN allaqachon Caddyfile da bor"
        else
            BACKUP="$CADDYFILE.bak-$(date +%F-%H%M)"
            cp "$CADDYFILE" "$BACKUP"
            printf '\n%s {\n\treverse_proxy ombor-crm:8000\n}\n' "$DOMAIN" >> "$CADDYFILE"
            echo "    $DOMAIN qo'shildi (zaxira: $BACKUP)"
        fi

        if docker exec "$CADDY" caddy validate --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
            # --force muhim: Caddyfile o'zgarmagan bo'lsa ham konteynerning yangi
            # IP manzili qayta aniqlanadi, aks holda eski IP ga urinib 502 beradi
            docker exec "$CADDY" caddy reload --config /etc/caddy/Caddyfile --force
            echo "    Caddy qayta yuklandi -> https://$DOMAIN"
        else
            echo "    OGOHLANTIRISH: Caddyfile validatsiyadan o'tmadi."
            echo "    Zaxiradan tiklang: cp $CADDYFILE.bak-* $CADDYFILE"
        fi
    else
        echo "    Caddyfile topilmadi — qo'lda qo'shing (deploy/Caddyfile ga qarang):"
        echo "      $DOMAIN { reverse_proxy ombor-crm:8000 }"
    fi

elif command -v nginx >/dev/null 2>&1; then
    sed "s|proxy_pass http://127.0.0.1:[0-9]*;|proxy_pass http://127.0.0.1:$WEB_PORT;|" \
        deploy/nginx-docker.conf > "/etc/nginx/sites-available/$DOMAIN"
    ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
    nginx -t

    if systemctl is-active --quiet nginx; then
        systemctl reload nginx
        echo "    $DOMAIN -> 127.0.0.1:$WEB_PORT"
    elif systemctl start nginx 2>/dev/null; then
        systemctl enable nginx >/dev/null 2>&1 || true
        echo "    nginx ishga tushirildi: $DOMAIN -> 127.0.0.1:$WEB_PORT"
    else
        echo "    OGOHLANTIRISH: nginx ishga tushmadi. 80-portni kim egallaganini ko'ring:"
        echo "      ss -ltnp | grep ':80 '"
    fi
else
    echo "    Na Caddy, na nginx topildi — docker nginx'ini ishlating:"
    echo "    docker compose --profile with-nginx up -d"
fi

# --------------------------------------------------------------------- 5. cron
echo "==> 5/5 Kunlik eslatmalar (cron)"
CRON_LINE="0 8 * * * cd $APP_DIR && docker compose exec -T web python manage.py check_deadlines >> /var/log/ombor-crm.log 2>&1"
( crontab -l 2>/dev/null | grep -v ombor-crm; echo "$CRON_LINE" ) | crontab -

echo
echo "TAYYOR"
echo "  Ichkarida: curl -I http://127.0.0.1:$WEB_PORT/api/docs/"
echo "  Domenda:   curl -I https://$DOMAIN/api/docs/"
echo
echo "Admin ochish:"
echo "  cd $APP_DIR && $COMPOSE exec web python manage.py createsuperuser"
