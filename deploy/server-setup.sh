#!/bin/bash
# Ombor CRM — serverga bitta komanda bilan o'rnatish (Docker).
#
#   cd /var/www/ombor-crm && sudo bash deploy/server-setup.sh
#
# Nima qiladi:
#   1. Docker yo'q bo'lsa o'rnatadi
#   2. .env bo'lmasa yaratadi, SECRET_KEY va WEB_PORT qo'yadi
#   3. Port bo'shligini tekshiradi va konteynerni ishga tushiradi
#   4. nginx saytini ombor.thesofmebel.uz uchun ulaydi (shu portga proxy)
#   5. Kunlik eslatmalar uchun cron qo'yadi
set -e

DOMAIN=ombor.thesofmebel.uz
APP_DIR=/var/www/ombor-crm
DEFAULT_PORT=8089

cd "$APP_DIR"

echo "==> 1/5 Docker"
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi

echo "==> 2/5 .env"
if [ ! -f .env ]; then
    cp .env.example .env
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env
    echo "    .env yaratildi, SECRET_KEY qo'yildi"
fi

# Eski .env da WEB_PORT bo'lmasligi mumkin — qo'shib qo'yamiz
if ! grep -q '^WEB_PORT=' .env; then
    echo "WEB_PORT=$DEFAULT_PORT" >> .env
    echo "    WEB_PORT=$DEFAULT_PORT qo'shildi"
fi

WEB_PORT=$(grep '^WEB_PORT=' .env | cut -d= -f2 | tr -d '[:space:]')
WEB_PORT=${WEB_PORT:-$DEFAULT_PORT}
echo "    port: 127.0.0.1:$WEB_PORT"

echo "==> 3/5 Konteyner"
# Port band bo'lsa, o'zimizning konteynerdan boshqasi ushlab turgan bo'lishi mumkin
if ss -ltn 2>/dev/null | grep -q ":$WEB_PORT "; then
    if docker ps --format '{{.Names}}' | grep -q '^ombor-crm$'; then
        echo "    portni o'z konteynerimiz ushlab turibdi — qayta ishga tushiriladi"
        docker compose down
    else
        echo
        echo "XATO: $WEB_PORT porti band (boshqa dastur ishlatyapti)."
        echo "      .env dagi WEB_PORT ni bo'sh portga o'zgartiring, masalan:"
        echo "      sed -i 's|^WEB_PORT=.*|WEB_PORT=8090|' $APP_DIR/.env"
        echo "      va skriptni qayta ishga tushiring."
        exit 1
    fi
fi

mkdir -p data media staticfiles
docker compose up -d --build

echo "==> 4/5 nginx"
if command -v nginx >/dev/null 2>&1; then
    sed "s|proxy_pass http://127.0.0.1:[0-9]*;|proxy_pass http://127.0.0.1:$WEB_PORT;|" \
        deploy/nginx-docker.conf > "/etc/nginx/sites-available/$DOMAIN"
    ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
    nginx -t

    # nginx o'chiq bo'lsa reload emas, start kerak
    if systemctl is-active --quiet nginx; then
        systemctl reload nginx
        echo "    $DOMAIN → 127.0.0.1:$WEB_PORT"
    elif systemctl start nginx 2>/dev/null; then
        systemctl enable nginx >/dev/null 2>&1 || true
        echo "    nginx ishga tushirildi: $DOMAIN → 127.0.0.1:$WEB_PORT"
    else
        echo
        echo "OGOHLANTIRISH: nginx ishga tushmadi. 80-portni kim egallaganini ko'ring:"
        echo "      ss -ltnp | grep ':80 '"
        echo "      systemctl status nginx --no-pager | head -20"
        echo "    Konteyner o'zi ishlayapti: http://127.0.0.1:$WEB_PORT/api/docs/"
    fi
else
    echo "    nginx yo'q — docker nginx'ini ishlating:"
    echo "    docker compose --profile with-nginx up -d"
fi

echo "==> 5/5 Kunlik eslatmalar (cron)"
CRON_LINE="0 8 * * * cd $APP_DIR && docker compose exec -T web python manage.py check_deadlines >> /var/log/ombor-crm.log 2>&1"
( crontab -l 2>/dev/null | grep -v ombor-crm; echo "$CRON_LINE" ) | crontab -

echo
echo "TAYYOR → http://$DOMAIN/api/docs/"
echo
echo "Tekshirish:"
echo "  curl -I http://127.0.0.1:$WEB_PORT/api/docs/"
echo "  docker compose logs -f web"
echo
echo "Admin ochish:"
echo "  cd $APP_DIR && docker compose exec web python manage.py createsuperuser"
echo
echo "HTTPS (domen serverga yo'naltirilgan bo'lsa):"
echo "  sudo certbot --nginx -d $DOMAIN"
