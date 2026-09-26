#!/bin/sh
# Konteyner ishga tushganda: migratsiya, static, kassa yacheykalari.
set -e

# 22-§1(c): WeasyPrint native kutubxonalarsiz IMPORT vaqtida yiqiladi, lekin
# u faqat birinchi PDF so'ralganda chaqiriladi (`render_contract_pdf` ichida
# lazy import) — shu sabab konteyner muammosiz ko'tariladi-yu, mijoz PDF
# so'raganda `500` beradi. Shu yerda bir marta sinab ko'rilsa, xato DEPLOY
# paytida chiqadi (konteyner apt paketlarisiz qurilgan bo'lsa).
echo "==> WeasyPrint tekshiruvi"
python -c "import weasyprint" || {
    echo "XATO: WeasyPrint kutubxonalari topilmadi (libpango/libcairo/libgdk-pixbuf) — Dockerfile'ga qarang."
    exit 1
}

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
