# 10 — Serverga o'rnatish

Ikki yo'l bor. **A — Docker** (eng oson, bitta komanda). **B — Docker'siz**: `/var/www/ombor-crm` + systemd + nginx.

Ikkalasida ham natija bir xil: **https://ombor.thesofmebel.uz/api/docs/** ochiladi,
static va media nginx orqali beriladi.

---

## A. Docker (tavsiya etiladi)

Domen: **ombor.thesofmebel.uz** · Papka: **/var/www/ombor-crm**

### 1. DNS

`ombor.thesofmebel.uz` uchun **A yozuvi** server IP siga qaratilgan bo'lsin.

### 2. Kodni serverga qo'yish

Termius'ning SFTP oynasi orqali `ombor-crm.zip` ni serverga tashlang, so'ng:

```bash
sudo mkdir -p /var/www/ombor-crm && sudo unzip -o ~/ombor-crm.zip -d /var/www/ombor-crm
```

### 3. Bitta komanda

```bash
cd /var/www/ombor-crm && sudo bash deploy/server-setup.sh
```

Skript: Docker yo'q bo'lsa o'rnatadi → `.env` yaratib yangi `SECRET_KEY` qo'yadi →
konteynerni yig'ib ishga tushiradi (migratsiya, static, kassa yacheykalari avtomatik) →
nginx saytini `ombor.thesofmebel.uz` ga ulaydi → kunlik eslatmalarni cron qiladi.

### 4. Admin foydalanuvchi

```bash
cd /var/www/ombor-crm && docker compose exec web python manage.py createsuperuser
```

### 5. HTTPS

```bash
sudo certbot --nginx -d ombor.thesofmebel.uz
```

Tayyor: **https://ombor.thesofmebel.uz/api/docs/**

### Nima qayerda ishlaydi

```
Internet :443/:80
   └── serverning nginx'i  (deploy/nginx-docker.conf)
         ├── /static/ , /media/  → /var/www/ombor-crm/{staticfiles,media}
         └── qolgani            → 127.0.0.1:8089   (.env dagi WEB_PORT)
                                     └── docker: ombor-crm (gunicorn, 3 worker)
                                           entrypoint: migrate → collectstatic → seed_finance
volumelar (host papkasi):
   /var/www/ombor-crm/data         → sqlite bazasi
   /var/www/ombor-crm/media        → yuklangan fayllar
   /var/www/ombor-crm/staticfiles  → static
```

Konteyner faqat `127.0.0.1:8089` da turadi — serverdagi boshqa saytlarga (`thesofmebel.uz`) tegmaydi.

> **Port band bo'lsa** (`address already in use`): `.env` dagi `WEB_PORT` ni o'zgartiring va
> `bash deploy/server-setup.sh` ni qayta ishga tushiring — nginx konfigi ham avtomatik shu portga moslanadi.
> Qaysi port band ekanini ko'rish: `ss -ltnp | grep 8089`.

> Serverda umuman nginx bo'lmasa: `docker compose --profile with-nginx up -d --build` —
> shunda 80-portni docker ichidagi nginx egallaydi.

### Agar serverda Caddy ishlayotgan bo'lsa

80/443 portlarni Caddy (yoki boshqa reverse proxy) egallagan bo'lsa, nginx kerak emas —
`server-setup.sh` buni o'zi aniqlaydi va:

1. `.env` ga `CADDY_NETWORK` ni yozadi
2. konteynerni `docker-compose.caddy.yml` bilan ko'taradi — shunda `ombor-crm` Caddy tarmog'ida
   ham bo'ladi va qayta yig'ilganda ham shu tarmoqda qoladi
3. Caddyfile ga blok qo'shadi (avval zaxira nusxa oladi), `caddy validate` qilib `caddy reload` beradi

Caddyfile ga qo'shiladigan blok ([deploy/Caddyfile](../deploy/Caddyfile)):

```
ombor.thesofmebel.uz {
    reverse_proxy ombor-crm:8000
}
```

TLS sertifikatini Caddy o'zi oladi — `certbot` shart emas.

Qo'lda qilmoqchi bo'lsangiz:

```bash
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
```

```bash
docker exec edu_platform-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```

> Static fayllarni **whitenoise** beradi, media fayllarni Django o'zi beradi (`SERVE_MEDIA=True`) —
> shuning uchun proxy tomonda alohida `file_server` sozlash shart emas.

### Sinov ma'lumotlari

```bash
docker compose exec web python manage.py seed_users
```

4 ta foydalanuvchi ochadi (parol: `Ombor2026!`):

| Login | Rol |
|---|---|
| `admin` | Administrator (superuser) |
| `bugalter` | Bugalter |
| `sales1` | Sales |
| `sales2` | Sales |

```bash
docker compose exec web python manage.py seed_clients
```

4 ta buyurtmachi: 2 jismoniy va 2 yuridik shaxs.

Parolni o'zingiz belgilash: `seed_users --password 'Kuchli-Parol1'`.
Mavjud foydalanuvchilar parolini qayta yozish: `--force`.

> Ochiq domenda turgan tizimda demo parollarni ishga tushgach almashtiring
> yoki keraksiz foydalanuvchilarni o'chiring.

### Kundalik ishlar

> `make` o'rnatilgan bo'lsa (`sudo apt install make`), shu jadvaldagilarni
> `make up`, `make logs`, `make deploy`, `make backup` deb qisqartirsa bo'ladi.

| Kerakli ish | Komanda (`/var/www/ombor-crm` ichida) |
|---|---|
| Holat | `docker compose ps` |
| Loglar | `docker compose logs -f web` |
| Qayta ishga tushirish | `docker compose restart web` |
| Kod yangilandi | `docker compose up -d --build` yoki `make deploy` |
| To'xtatish | `docker compose down` |
| Migratsiya | `docker compose exec web python manage.py migrate` |
| Eslatmalarni tekshirish | `docker compose exec web python manage.py check_deadlines` |
| Baza zaxirasi | `cp data/db.sqlite3 /var/backups/ombor-$(date +%F).sqlite3` |

---

## B. Docker'siz — /var/www + systemd + nginx

Kodni `/var/www/ombor-crm` ga qo'ying, so'ng:

```bash
sudo bash /var/www/ombor-crm/deploy/deploy.sh
```

Skript nima qiladi:

1. `python3-venv`, `pip`, `nginx` ni o'rnatadi
2. `.venv` yaratib `requirements.txt` ni o'rnatadi
3. `.env` bo'lmasa `.env.example` dan yaratadi va yangi `SECRET_KEY` qo'yadi
4. `migrate`, `collectstatic`, `seed_finance`
5. `deploy/ombor-crm.service` ni systemd'ga qo'yadi va ishga tushiradi
6. `deploy/ombor-crm-nginx.conf` ni nginx sayti qilib ulaydi
7. `check_deadlines` ni har kuni soat 8:00 ga cron qilib qo'yadi

> Muhim: `.env` da `SQLITE_PATH` qatorini **o'chirib tashlang** — Docker'siz variantda baza
> `/var/www/ombor-crm/db.sqlite3` da turadi.

| Kerakli ish | Komanda |
|---|---|
| Holat | `systemctl status ombor-crm` |
| Loglar | `journalctl -u ombor-crm -f` |
| Qayta ishga tushirish | `systemctl restart ombor-crm` |
| nginx tekshirish | `nginx -t && systemctl reload nginx` |
| Admin ochish | `cd /var/www/ombor-crm && .venv/bin/python manage.py createsuperuser` |

### Kod yangilanganda

```bash
cd /var/www/ombor-crm && .venv/bin/pip install -r requirements.txt && .venv/bin/python manage.py migrate && .venv/bin/python manage.py collectstatic --noinput && systemctl restart ombor-crm
```

---

## HTTPS (ixtiyoriy, domen bo'lsa)

```bash
sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx -d ombor.thesofmebel.uz
```

Docker variantida sertifikat uchun nginx'ni server ustida qoldirib, `docker compose` dagi
nginx portini `127.0.0.1:8080:80` ga o'zgartirish qulayroq.

---

## Sozlamalar (.env)

| O'zgaruvchi | Ma'nosi | Default |
|---|---|---|
| `SECRET_KEY` | Django maxfiy kaliti | dev kaliti (serverda albatta almashtiring) |
| `DEBUG` | Xatolarni ko'rsatish | `True` (serverda `False`) |
| `ALLOWED_HOSTS` | Ruxsat etilgan domen/IP, vergul bilan | `*` |
| `CSRF_TRUSTED_ORIGINS` | Admin panel uchun domen | bo'sh |
| `CORS_ALLOWED_ORIGINS` | React manzili | `http://localhost:5173,http://127.0.0.1:5173` |
| `WEB_PORT` | Docker konteyneri turadigan port (127.0.0.1) | `8089` |
| `CADDY_NETWORK` | Caddy docker tarmog'i (skript o'zi to'ldiradi) | — |
| `SERVE_MEDIA` | Media fayllarni Django bersinmi | `True` |
| `SQLITE_PATH` | Baza fayli yo'li | `<loyiha>/db.sqlite3` |
| `DJANGO_SUPERUSER_*` | Birinchi ishga tushishda admin ochish | bo'sh |

O'qilishi: `root/settings/env.py` → `base.py`, `database.py`, `cors.py`.

---

## Tekshirish

```bash
curl -I https://ombor.thesofmebel.uz/api/docs/
```

`200 OK` kelsa — tayyor. Keyin `POST /api/auth/login/` orqali token oling ([05-API.md](05-API.md)).

## Zaxira (backup)

Baza — bitta fayl, shuning uchun zaxira oson:

```bash
0 3 * * * cp /var/www/ombor-crm/db.sqlite3 /var/backups/ombor-crm-$(date +\%F).sqlite3
```

Docker variantida:

```bash
docker compose cp web:/app/data/db.sqlite3 ./backup-$(date +%F).sqlite3
```
