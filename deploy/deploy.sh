#!/bin/bash
# Docker'siz o'rnatish: /var/www/ombor-crm + systemd + nginx
#
#   sudo bash deploy/deploy.sh
#
# Kod allaqachon /var/www/ombor-crm ga ko'chirilgan bo'lishi kerak.
set -e

APP_DIR=/var/www/ombor-crm
APP_USER=www-data

echo "==> Kerakli paketlar"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip nginx

echo "==> Virtual muhit va kutubxonalar"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

echo "==> .env tekshirilmoqda"
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    SECRET=$(.venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" "$APP_DIR/.env"
    echo "    .env yaratildi — ALLOWED_HOSTS ni domeningizga moslang"
fi

echo "==> Migratsiya, static, kassa yacheykalari"
set -a
. "$APP_DIR/.env"
set +a
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py seed_finance

echo "==> Ruxsatlar"
mkdir -p "$APP_DIR/media" "$APP_DIR/staticfiles"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> systemd xizmati"
cp "$APP_DIR/deploy/ombor-crm.service" /etc/systemd/system/ombor-crm.service
systemctl daemon-reload
systemctl enable ombor-crm
systemctl restart ombor-crm

echo "==> nginx"
cp "$APP_DIR/deploy/ombor-crm-nginx.conf" /etc/nginx/sites-available/ombor-crm
ln -sf /etc/nginx/sites-available/ombor-crm /etc/nginx/sites-enabled/ombor-crm
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> Kunlik eslatmalar (cron)"
CRON_LINE="0 8 * * * cd $APP_DIR && $APP_DIR/.venv/bin/python manage.py check_deadlines >> /var/log/ombor-crm-deadlines.log 2>&1"
( crontab -l 2>/dev/null | grep -v check_deadlines; echo "$CRON_LINE" ) | crontab -

echo
echo "TAYYOR. Holat:  systemctl status ombor-crm"
echo "Loglar:         journalctl -u ombor-crm -f"
echo "Admin ochish:   cd $APP_DIR && .venv/bin/python manage.py createsuperuser"
