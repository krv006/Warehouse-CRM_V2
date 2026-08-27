#!/bin/sh
# Konteyner ishga tushganda: migratsiya, static, kassa yacheykalari.
set -e

echo "==> Migratsiyalar"
python manage.py migrate --noinput

echo "==> Static fayllar"
python manage.py collectstatic --noinput

echo "==> Kassa kategoriyalari"
python manage.py seed_finance

# DJANGO_SUPERUSER_USERNAME / _PASSWORD / _EMAIL berilgan bo'lsa, admin ochiladi
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "==> Superuser tekshirilmoqda"
    python manage.py createsuperuser --noinput || true
fi

echo "==> Server ishga tushmoqda"
exec "$@"
