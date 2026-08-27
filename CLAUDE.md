# Ombor CRM (Warehouse_CRM_V2) — loyiha qoidalari va tuzilishi

> To'liq hujjatlar: [docs/](docs/README.md) — arxitektura, biznes qoidalar, rollar,
> ma'lumotlar modeli, API, jarayonlar, kod uslubi, testlar, React qo'llanmasi.

Django 6.1 + DRF backend. Frontend keyinchalik React (Vite, `localhost:5173` CORS'da ochilgan).
Config paketi: `root/`. Barcha ilovalar: `apps/`.

## 1. Kod qoidalari (majburiy)

### 1.1 Papka tuzilishi

```
apps/
    urls.py            <-- barcha app urls.py larini yig'adi
apps/<app>/
    __init__.py
    apps.py
    admin.py
    permissions.py     <-- kerak bo'lsa
    serializers.py
    services.py        <-- biznes logika (view'da emas)
    urls.py            <-- shu ilovaning marshrutlari (path, router yo'q)
    views.py
    models/            <-- papka, models.py EMAS
        __init__.py    <-- barcha modellarni re-export qiladi
        <model>.py     <-- har bir model alohida faylda
    tests/             <-- papka, tests.py EMAS
        __init__.py
        test_<nima>.py
    migrations/
```

### 1.2 Import uslubi — prefikssiz

```python
# TO'G'RI
from django.db.models import CharField, ForeignKey, CASCADE
name = CharField(max_length=150)

# NOTO'G'RI
from django.db import models
name = models.CharField(max_length=150)
```

Bu qoida `models/`, `serializers.py`, `views.py`, `admin.py` — hamma joyda amal qiladi.

### 1.3 ForeignKey — doim aniq "app.Model" satri

```python
category = ForeignKey('inventory.Category', PROTECT, related_name='products')
```

- Birinchi argument — `'<app_label>.<ModelName>'` satri, klass obyekti emas.
- `on_delete` — pozitsion argument (`CASCADE`, `PROTECT`, `SET_NULL`), qavssiz.
- `related_name` — har doim ko'rsatiladi.

### 1.4 Model / View / Serializer

- Barcha modellar `apps.core.models.TimeStampedModel` dan meros oladi (`User` dan tashqari).
- Tanlovlar — model ichidagi `TextChoices` klassi.
- Har bir model va klassda o'zbekcha docstring va `__str__`.
- ViewSet'lar `apps.core.mixins.BaseModelViewSet` dan meros oladi — u `created_by` ni yozadi va
  har bir amalni `ActivityLog` ga audit qilib qo'yadi.
- `queryset` da doim `select_related` / `prefetch_related`; `search_fields`,
  `filterset_fields`, `ordering_fields` deklarativ.

### 1.5 Marshrutlar

**Router ishlatilmaydi.** Har bir ilova o'z `urls.py` sida manzillarni `path()` bilan aniq yozadi:

```python
from apps.core.routing import DETAIL, LIST

urlpatterns = [
    path('products/', ProductViewSet.as_view(LIST), name='product-list'),
    path('products/<int:pk>/', ProductViewSet.as_view(DETAIL), name='product-detail'),
    path('contracts/<int:pk>/confirm-payment/', ContractViewSet.as_view({
        'post': 'confirm_payment',
    }), name='contract-confirm-payment'),
]
```

- Metod xaritalari: `apps/core/routing.py` — `LIST`, `DETAIL`, `READ_LIST`, `READ_DETAIL`.
- `@action` dekoratori ishlatilmaydi; amalga alohida ruxsat kerak bo'lsa `get_permissions()` da
  `self.action` bo'yicha beriladi.
- `pk` doim `<int:pk>`; nom berish: `<model>-list`, `<model>-detail`, `<model>-<amal>`.
- `apps/urls.py` har bir ilovani bitta qator bilan ulaydi: `path('', include('apps.<app>.urls'))`.
- `root/urls.py` faqat `admin/`, `api/` → `include('apps.urls')` va schema/docs ni biladi.
- `app_name` qo'yilmaydi — endpoint nomlari global qoladi.

## 2. Biznes mantiq (TZ asosida)

### 2.1 Rollar — `apps/accounts`

| Rol | Vazifasi |
|---|---|
| `admin` | Hamma narsani ko'radi, ACT kiritadi, shartnomani oxirgi tasdiqlaydi, bugalterning xarajatiga ruxsat beradi |
| `bugalter` | Hujjat va pul kirdi-chiqdisi, shartnomaning 1-tasdig'i, pul kelganini tasdiqlash. Client qo'sha olmaydi |
| `sales` | Zakaz shakllantiradi, configurator qiladi, client qo'shadi, sotuv narxini ko'radi |

Permission klasslari: `apps/accounts/permissions.py` (`IsAdmin`, `IsAdminOrBugalter`,
`IsAdminOrSales`, `CanManageClients`, `IsAdminOrReadOnly`).

### 2.2 Client — `apps/clients`

Bitta model, ikki tur: `individual` (F.I.SH, passport, JSHSHIR — unique) va
`legal` (kompaniya nomi, INN, JSHSHIR, rahbar F.I.SH, manzil — majburiy).
`phone` — hamma uchun unique, `email` va `note` — optional.

### 2.3 Kirim — `apps/purchases`

`Purchase.type`: `local` (UZB ichidan), `import`, `ustav` (USTAF — bojxona boji va soliq maydonlari).
`lead_days` + `ordered_at` → `expected_at` va line chart (`GET /api/purchases/{id}/timeline/`).
`POST /api/purchases/{id}/receive/` — omborga kirim yozadi va kassaga chiqim tushiradi.

### 2.4 Chiqim va Kassa — `apps/finance`

- `CashCategory` — yacheykalar: kirim (`sale`, `ustav_in`, `loan`), chiqim (`import`,
  `contract_invoice`, `ustav_out`, `salary`, `rent`, `meal`, `loan_repay`, `other`).
  Yangi yacheyka qo'shish mumkin (`POST /api/cash-categories/`).
- `CashTransaction` — har bir kirim/chiqim; `direction` kategoriyadan olinadi.
- `Loan` — qarz: summa, deadline, eslatma, `repay` action.
- `ExpenseRequest` — bugalter so'raydi, **faqat admin** `approve`/`reject` qiladi;
  ruxsatdan keyin avtomatik chiqim yoziladi.

### 2.5 Sales — `apps/sales`

- `Lead` — og'zaki kelishuv jarayoni (`new → negotiation → verbal → contract / lost`).
- `Contract` holatlari:
  `draft → pending_bugalter → pending_admin → approved → active → completed`
  (`rejected`, `cancelled`).
  - `POST /contracts/{id}/submit/` — sales yuboradi
  - `POST /contracts/{id}/approve/` — avval bugalter, keyin admin
  - `POST /contracts/{id}/confirm-payment/` — bugalter; shu kundan **muddat sanog'i** boshlanadi
  - `GET /contracts/{id}/timeline/` — line chart nuqtalari va rang
- Oldindan to'lov: summa **1 mlrd dan kam bo'lsa 30%**, ko'p bo'lsa **15%**; qo'lda o'zgartirsa bo'ladi.
- Rang qoidasi (`apps/core/utils.py`): yashil → sariq (oxirgi 30%) → **oxirgi 10 kun qizil**.
- Qator narxi (`unit_price`, `subtotal`) faqat sales va adminga ko'rinadi.

### 2.6 Configurator — `apps/configurator`

Barcha rollarga ochiq. Bazaviy model (`Product.kind = machine`) tarkibi `ProductSpec` da.
`Configuration` + `ConfigurationItem`: har bir qator uchun `available` / `shortage` / `source`
(`stock` yoki `purchase`) hisoblanadi.
- `GET /configurations/{id}/stock-check/`
- `POST /configurations/{id}/finalize/` — **ACT majburiy** (ACT ni faqat admin kiritadi)
- `POST /configurations/{id}/attach/` — tayyor konfiguratsiyani kirim buyurtmasiga biriktiradi
- `GET /configurations/{id}/export-excel/` — chernovik Excel (openpyxl)

### 2.7 Audit va eslatmalar — `apps/core`

- `ActivityLog` — kim, qachon, nima qilgani (faqat admin ko'radi: `/api/activity-logs/`).
- `Notification` + `python manage.py check_deadlines` — shartnoma, qarz va import
  muddatlari bo'yicha eslatma yaratadi (idempotent).
- `GET /api/dashboard/` — kassa, kirim, sales, clients, ombor, deadlines, notifications.

## 3. Ishga tushirish

```bash
.venv/Scripts/python.exe manage.py migrate
```

```bash
.venv/Scripts/python.exe manage.py seed_finance
```

```bash
.venv/Scripts/python.exe manage.py test apps
```

```bash
.venv/Scripts/python.exe manage.py check_deadlines
```

API hujjati: `/api/docs/`, JWT: `POST /api/auth/login/`.

## 4. Keyingi bosqich (hali qilinmagan)

- Export (valyuta: USD / EUR / CNY) — modelda `currency` va `exchange_rate` joyi tayyor, jarayoni yozilmagan.
- React frontend (Vite, `localhost:5173`).
- Bojxona/soliq tizimlari bilan real integratsiya (hozircha `customs_duty` va `tax_amount` qo'lda).
