FROM python:3.13-slim

# SQLITE_PATH shu yerda turadi — shunda `docker compose exec` bilan ishga tushirilgan
# komandalar ham aynan shu bazani ochadi (.env dagi qiymat baribir ustun keladi).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=root.settings \
    SQLITE_PATH=/app/data/db.sqlite3

WORKDIR /app

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
