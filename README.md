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

## Raqamlarda

| Ko'rsatkich | Qiymat |
|---|---|
| REST endpoint | **92 endpoint** (Swagger va OpenAPI sahifalaridan tashqari) |
| Django ilovalari | 9 ta (`core`, `accounts`, `clients`, `inventory`, `configurator`, `purchases`, `procurement`, `sales`, `finance`) |
| Modellar | 30 ta |
| Rollar | 5 ta: admin, bugalter, sales, buyurtmachi, engineer |
| Testlar | **176 ta**, hammasi o'tadi |

---

## Serverdagi holat

Tizim ishlab turibdi: **https://ombor.thesofmebel.uz**

| Manzil | Nima |
|---|---|
| https://ombor.thesofmebel.uz/api/docs/ | Swagger — barcha endpointlar |
| https://ombor.thesofmebel.uz/api/schema/ | OpenAPI (frontend uchun TS tiplari) |
| https://ombor.thesofmebel.uz/admin/ | Django admin |

`make docker-demo` bitta komanda bilan **butun tizimga** demo yuklaydi: 5 foydalanuvchi,
4 mijoz, 5 mahsulot (qoldiq bilan), 5 lead, 5 shartnoma (har bosqichdan), 5 kirim
(har turdan), 2 to'ldirish hisobi, qarzlar, xarajatlar va eslatmalar.
Foydalanuvchilar, parol — `Ombor2026!`:

| Login | Rol |
|---|---|
| `admin` | Administrator (superuser) |
| `bugalter` | Bugalter |
| `buyurtmachi` | Buyurtmachi |
| `engineer` | Engineer (configurator ishlari) |
| `sales1`, `sales2` | Sales |

> Bu sinov parollari kodda ham turibdi (`seed_users.py`). Haqiqiy ishga o'tishda
> `manage.py changepassword <login>` bilan almashtiring yoki keraksizlarini o'chiring.

Kodni yangilash (Caddy bilan to'g'ri ishlashi uchun aynan shu):

```bash
cd /var/www/ombor-crm && git pull origin main && make deploy
```

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
| [docs/11-FRONTEND-SCREENS.md](docs/11-FRONTEND-SCREENS.md) | Ekranlar bo'yicha topshiriq (frontend) |
| [docs/12-CHANGELOG-TZ-2.1.md](docs/12-CHANGELOG-TZ-2.1.md) | TZ 2.1 o'zgarishlari |
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
│   ├── inventory/        # Warehouse, Product, ProductSpec, Stock, StockMovement (API: faqat o'qish)
│   ├── configurator/     # Act, Configuration, ConfigurationItem, Excel eksport
│   ├── purchases/        # Kirim: UZB ichidan / Import / Ustav
│   ├── procurement/      # Buyurtmachi: omborni to'ldirish, qarz, yetkazib berish
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
| `make demo` | to'liq demo: userlar, mijozlar, mahsulotlar, shartnomalar, kirim, kassa |
| `make demo-reset` | bazani **tozalab** demo'ni qaytadan yuklaydi (akkauntlar qoladi) |
| `make stock` | kam qolgan mahsulotlarga demo kirim — har biriga kamida 10 dona |
| `make migrations` / `make migrate` | migratsiya yozish / qo'llash |
| `make clean` | `__pycache__` tozalash |

| Serverda (docker) | Nima qiladi |
|---|---|
| `make up` | yig'ib ishga tushiradi |
| `make logs` | jonli loglar |
| `make deploy` | git pull + to'liq o'rnatish (konteyner, Caddy, cron) |
| `make docker-dbcheck` | qaysi baza ishlatilayotgani va migratsiya holati |
| `make docker-superuser` | konteyner ichida admin ochish |
| `make docker-demo` | serverda to'liq demo ma'lumotlar |
| `make docker-demo-reset` | serverda bazani tozalab demo'ni qaytadan yuklaydi |
| `make docker-stock` | serverda kam qolgan mahsulotlarga demo kirim yozadi |
| `make backup` | bazani zaxiralaydi |

---

## Management komandalar

```bash
.venv/Scripts/python.exe manage.py seed_finance
```
Kassa yacheykalarini yaratadi (sotuv, ustav, qarz, import, oylik, arenda, obed, ...).

```bash
.venv/Scripts/python.exe manage.py seed_stock
```
Kam qolgan mahsulotlarga demo kirim yozadi (sinov uchun): har bir faol mahsulot
yagona omborda kamida 10 dona bo'ladi. Idempotent — qayta yursa ortiqcha qo'shmaydi.

```bash
.venv/Scripts/python.exe manage.py check_deadlines
```
Shartnoma, qarz va import muddatlarini tekshirib eslatma (Notification) yaratadi. Cron/Task Scheduler'ga kunlik qo'yiladi.

```bash
.venv/Scripts/python.exe manage.py test apps
```
Barcha testlar (176 ta).

---

## Holat

| Bo'lim | Holat |
|---|---|
| Kirim (UZB / Import / Ustav) | ✅ tayyor |
| Chiqim va Kassa | ✅ tayyor |
| Sales + shartnoma approve zanjiri | ✅ tayyor |
| Configurator + ACT + Excel | ✅ tayyor |
| Client (jismoniy / yuridik) | ✅ tayyor |
| Buyurtmachi moduli (to'ldirish, qarz, yetkazib berish) | ✅ tayyor |
| Rollar (5 ta), audit, eslatmalar | ✅ tayyor |
| Export (USD / EUR / CNY) | 🟡 modelda joy bor, jarayon yozilmagan |
| Serverga o'rnatish (Docker / systemd + nginx) | ✅ tayyor |
| React frontend | ⬜ keyingi bosqich |
| Serverga o'rnatildi (ombor.thesofmebel.uz, Caddy + HTTPS) | ✅ ishlab turibdi |
| Bojxona / soliq integratsiyasi | ⬜ hozircha qo'lda kiritiladi |
