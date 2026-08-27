# Ombor CRM (Warehouse CRM V2)

Ombor + CRM + Sotuv tizimi. Backend — **Django 6.1 + Django REST Framework**, frontend — **React** (keyingi bosqich).

Tizim TZ bo'yicha ikkita katta bo'lakdan iborat: **Kirim** va **Chiqim**, ular ustidan **Kassa** nazorat qiladi.
Sotuv jarayoni **Sales → Bugalter → Admin → To'lov** zanjiri bilan yuritiladi, mahsulot tarkibi esa
**Configurator** orqali ACT hujjati asosida o'zgartiriladi.

---

## Tez boshlash

```bash
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

```bash
.venv/Scripts/python.exe manage.py migrate
```

```bash
.venv/Scripts/python.exe manage.py seed_finance
```

```bash
.venv/Scripts/python.exe manage.py createsuperuser
```

```bash
.venv/Scripts/python.exe manage.py runserver
```

| Manzil | Nima |
|---|---|
| `http://127.0.0.1:8000/api/docs/` | Swagger — barcha endpointlar |
| `http://127.0.0.1:8000/api/schema/` | OpenAPI schema (React uchun) |
| `http://127.0.0.1:8000/admin/` | Django admin |

Login: `POST /api/auth/login/` → `{"access": "...", "refresh": "..."}`, so'ngra `Authorization: Bearer <access>`.

---

## Hujjatlar

| Fayl | Nima haqida |
|---|---|
| [docs/01-ARCHITECTURE.md](docs/01-ARCHITECTURE.md) | Papka tuzilishi, ilovalar, qatlamlar |
| [docs/02-BUSINESS-RULES.md](docs/02-BUSINESS-RULES.md) | TZ qoidalari: Kirim, Chiqim, Kassa, foizlar, ranglar |
| [docs/03-ROLES-PERMISSIONS.md](docs/03-ROLES-PERMISSIONS.md) | Admin / Bugalter / Sales — kim nima qila oladi |
| [docs/04-DATA-MODEL.md](docs/04-DATA-MODEL.md) | Barcha modellar va maydonlar |
| [docs/05-API.md](docs/05-API.md) | To'liq endpoint ro'yxati, so'rov va javob namunalari |
| [docs/06-WORKFLOWS.md](docs/06-WORKFLOWS.md) | Shartnoma, Configurator, Kirim va Kassa jarayonlari (diagrammalar) |
| [docs/07-CODE-STYLE.md](docs/07-CODE-STYLE.md) | Kod yozish qoidalari (majburiy) |
| [docs/08-TESTING.md](docs/08-TESTING.md) | Testlar, komandalar |
| [docs/09-FRONTEND-REACT.md](docs/09-FRONTEND-REACT.md) | React integratsiyasi uchun qo'llanma |
| [docs/10-DEPLOY.md](docs/10-DEPLOY.md) | Serverga o'rnatish: Docker yoki systemd + nginx |
| [CLAUDE.md](CLAUDE.md) | AI yordamchi uchun qisqa qoidalar to'plami |

---

## Loyiha tuzilishi

```
Warehouse_CRM_V2/
├── root/                 # settings/ (bo'laklarga bo'lingan), urls (→ apps.urls), wsgi/asgi
├── apps/
│   ├── urls.py           # barcha app'larning urls.py fayllarini yig'adi
│   ├── core/             # TimeStampedModel, ActivityLog, Notification, Dashboard
│   ├── accounts/         # User (admin/bugalter/sales), permissions
│   ├── clients/          # Client — jismoniy va yuridik shaxs
│   ├── inventory/        # Category, Warehouse, Product, ProductSpec, Stock, StockMovement
│   ├── configurator/     # Act, Configuration, ConfigurationItem, Excel eksport
│   ├── purchases/        # Kirim: UZB ichidan / Import / Ustav
│   ├── sales/            # Lead, Contract, ContractItem, Approval, Payment
│   └── finance/          # Kassa: kategoriya, tranzaksiya, qarz, xarajat so'rovi
├── deploy/               # entrypoint, nginx, systemd service, deploy.sh
├── Makefile              # qisqa komandalar (make, make test, make up ...)
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── templates/
├── requirements.txt
└── manage.py
```

Har bir ilovada `models/` va `tests/` — papka ko'rinishida, `urls.py` esa har bir app'da alohida
([docs/07-CODE-STYLE.md](docs/07-CODE-STYLE.md)).

---

## Makefile — qisqa komandalar

`make` bo'lsa, hamma narsa qisqaradi (`make` — ro'yxatni ko'rsatadi):

| Lokal | Nima qiladi |
|---|---|
| `make setup` | install + migrate + seed (birinchi ishga tushirish) |
| `make run` | lokal server |
| `make test` | barcha testlar |
| `make ci` | check + test (commitdan oldin) |
| `make superuser` | admin ochish |
| `make migrations` / `make migrate` | migratsiya yozish / qo'llash |
| `make clean` | `__pycache__` tozalash |

| Serverda (docker) | Nima qiladi |
|---|---|
| `make up` | yig'ib ishga tushiradi |
| `make logs` | jonli loglar |
| `make deploy` | git pull + qayta yig'ish + migratsiya |
| `make docker-superuser` | konteyner ichida admin ochish |
| `make backup` | bazani zaxiralaydi |

---

## Management komandalar

```bash
.venv/Scripts/python.exe manage.py seed_finance
```
Kassa yacheykalarini yaratadi (sotuv, ustav, qarz, import, oylik, arenda, obed, ...).

```bash
.venv/Scripts/python.exe manage.py check_deadlines
```
Shartnoma, qarz va import muddatlarini tekshirib eslatma (Notification) yaratadi. Cron/Task Scheduler'ga kunlik qo'yiladi.

```bash
.venv/Scripts/python.exe manage.py test apps
```
Barcha testlar (56 ta).

---

## Holat

| Bo'lim | Holat |
|---|---|
| Kirim (UZB / Import / Ustav) | ✅ tayyor |
| Chiqim va Kassa | ✅ tayyor |
| Sales + shartnoma approve zanjiri | ✅ tayyor |
| Configurator + ACT + Excel | ✅ tayyor |
| Client (jismoniy / yuridik) | ✅ tayyor |
| Rollar, audit, eslatmalar | ✅ tayyor |
| Export (USD / EUR / CNY) | 🟡 modelda joy bor, jarayon yozilmagan |
| Serverga o'rnatish (Docker / systemd + nginx) | ✅ tayyor |
| React frontend | ⬜ keyingi bosqich |
| Bojxona / soliq integratsiyasi | ⬜ hozircha qo'lda kiritiladi |
