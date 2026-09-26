FROM python:3.13-slim

# SQLITE_PATH shu yerda turadi — shunda `docker compose exec` bilan ishga tushirilgan
# komandalar ham aynan shu bazani ochadi (.env dagi qiymat baribir ustun keladi).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=root.settings \
    SQLITE_PATH=/app/data/db.sqlite3

WORKDIR /app

# 22-§1: WeasyPrint sof Python paket emas — u ishga tushganda (import
# vaqtida) libgobject/libpango/libharfbuzz/libcairo/libgdk-pixbuf ni
# tizimdan izlaydi. `python:3.13-slim`da bular yo'q — shu sabab PDF
# jonli serverda `500` berardi (Django bemalol ko'tarilardi, chunki
# import `render_contract_pdf` funksiyasi ICHIDA — birinchi PDF
# so'ralganda sezilardi). `fonts-dejavu-core` — `_CONTRACT_PDF_CSS`dagi
# `font-family: DejaVu Sans` uchun; shriftsiz kirill matn buziladi.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
        libcairo2 libgdk-pixbuf-2.0-0 libffi8 \
        shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Windows'da yozilgan skriptlar CRLF bilan kelishi mumkin — tozalab qo'yamiz
RUN sed -i 's/\r$//' deploy/entrypoint.sh && chmod +x deploy/entrypoint.sh

# Baza, media va static uchun papkalar (docker volume shu yerga ulanadi)
RUN mkdir -p /app/data /app/media /app/staticfiles

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "root.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-"]
