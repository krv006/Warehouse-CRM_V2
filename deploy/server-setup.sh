#!/bin/bash
# Ombor CRM — serverga bitta komanda bilan o'rnatish (Docker).
#
#   cd /var/www/ombor-crm && sudo bash deploy/server-setup.sh
#
# Nima qiladi:
#   1. Docker yo'q bo'lsa o'rnatadi
#   2. .env bo'lmasa yaratadi va yangi SECRET_KEY qo'yadi
#   3. Konteynerni yig'ib ishga tushiradi (127.0.0.1:8000)
#   4. nginx saytini ombor.thesofmebel.uz uchun ulaydi
#   5. Kunlik eslatmalar uchun cron qo'yadi
set -e

DOMAIN=ombor.thesofmebel.uz
APP_DIR=/var/www/ombor-crm

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

echo "==> 3/5 Konteyner"
mkdir -p data media staticfiles
docker compose up -d --build

echo "==> 4/5 nginx"
if command -v nginx >/dev/null 2>&1; then
    cp deploy/nginx-docker.conf "/etc/nginx/sites-available/$DOMAIN"
    ln -sf "/etc/nginx/sites-available/$DOMAIN" "/etc/nginx/sites-enabled/$DOMAIN"
    nginx -t
    systemctl reload nginx
    echo "    $DOMAIN sayti ulandi"
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
echo "Admin ochish:"
echo "  cd $APP_DIR && docker compose exec web python manage.py createsuperuser"
echo
echo "HTTPS (domen serverga yo'naltirilgan bo'lsa):"
echo "  sudo certbot --nginx -d $DOMAIN"
