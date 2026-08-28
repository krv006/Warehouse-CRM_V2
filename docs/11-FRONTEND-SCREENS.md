# 11 — Ekranlar bo'yicha topshiriq (frontend)

Har bir ekran uchun: kim ko'radi, qaysi endpoint, qanday maydon, qanday holat.
Texnik kontrakt (auth, xatolar, ranglar): [09-FRONTEND-REACT.md](09-FRONTEND-REACT.md).

Belgilar: ✅ yozadi · 👁 faqat ko'radi · ⛔ ochilmaydi (GET ham `403`)

---

## 0. Kirish va karkas

### 0.1 Login

`POST /auth/login/` → `{access, refresh}` → `GET /users/me/`

Xato: `401` → "Login yoki parol noto'g'ri".

### 0.2 Sidebar (rol bo'yicha)

| Menyu | admin | bugalter | sales | buyurtmachi | engineer |
|---|:--:|:--:|:--:|:--:|:--:|
| Dashboard | ✅ | ✅ | ✅ | ✅ | ✅ |
| Sotuv (Leads, Shartnomalar) | ✅ | ✅ | ✅ | 👁 | 👁 |
| Zayavkalar | ✅ | 👁 | ✅ yozadi | 👁 | ✅ bajaradi |
| To'ldirish (Buyurtmachi) | ✅ | ✅ | ⛔ | ✅ | ⛔ |
| Ombor | 👁 | 👁 | 👁 | 👁 | 👁 |
| Configurator | ✅ | 👁 | 👁 | 👁 | ✅ yozadi |
| Kirim | ✅ | ✅ | ⛔ | 👁 | ⛔ |
| Kassa | ✅ | ✅ | ⛔ | ⛔ | ⛔ |
| Mijozlar | ✅ | 👁 | ✅ | ✅ | 👁 |
| ACT | ✅ | 👁 | 👁 | 👁 | 👁 |
| Foydalanuvchilar | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |
| Audit | ✅ | ⛔ | ⛔ | ⛔ | ⛔ |

Yuqori panelda: eslatmalar qo'ng'irog'i (`GET /notifications/?is_read=false`), foydalanuvchi nomi va roli.

---

## 1. Dashboard

**Endpoint:** `GET /dashboard/` (bitta so'rov)

**Bloklar:**

1. **Kassa kartalari** — `kassa.income_total`, `kassa.expense_total`, `kassa.balance`
2. **Kirim/chiqim doiraviy grafigi** — `kassa.income_by_category`, `kassa.expense_by_category`
3. **Oylik tushum chizig'i** — `sales.monthly_income` (`month`, `total`)
4. **Shartnomalar holati** — `sales.contracts_by_status` (status bo'yicha ustunlar)
5. **Muddatlar jadvali** — `deadlines[]`: `number`, `client`, `days_left`, `color`, `balance`
   → qatorni `color` bo'yicha bo'yang, bosilganda shartnomaga o'ting
6. **Yetishmayotgan mahsulot** — `ombor.low_stock[]` → "To'ldirish hisobini yaratish" tugmasi
7. **Yo'ldagi importlar** — `kirim.in_transit` soni
8. **Eslatmalar** — `notifications[]`

Admin uchun hammasi, boshqa rollar uchun ham shu endpoint ishlaydi (ma'lumot bir xil).

---

## 2. Sotuv (Sales)

### 2.1 Leads — og'zaki kelishuvlar

**Ro'yxat:** `GET /leads/` · filtr `?stage=`, `?client=` · qidiruv `?search=`

**Kanban** (tavsiya): `new → negotiation → verbal → contract`, yon tomonda `lost`.
Bosqichni o'zgartirish: `PATCH /leads/{id}/ {"stage": "verbal"}`

**Maydonlar:** `title`, `client` (select), `expected_amount`, `next_contact_at`, `note`

**Ruxsat:** sales/admin ✅, boshqalar 👁

### 2.2 Shartnomalar ro'yxati

**Endpoint:** `GET /contracts/` · filtr `?status=`, `?client=`, `?currency=`

**Ustunlar:** `number`, `client_name`, `status_display`, `total_amount`, `paid`, `balance`,
`days_left` + `color` nuqtasi

### 2.3 Shartnoma kartasi

**Endpoint:** `GET /contracts/{id}/`

**Bo'limlar:**

| Blok | Maydonlar |
|---|---|
| Shapka | `number`, `status_display`, `client_name`, `signed_at`, `term_days` |
| Summa | `total_amount`, `prepayment_percent`, `prepayment_amount`, `paid`, `balance` |
| Qatorlar | `items[]`: `product_name`, `quantity`, `unit_price`*, `subtotal`* |
| To'lovlar | `payments[]`: `amount`, `method_display`, `paid_at`, `is_prepayment` |
| Tasdiqlar | `approvals[]`: `step_display`, `decision_display`, `decided_by_name`, `comment` |
| Muddat grafigi | `GET /api/contracts/{id}/timeline/` → `points[]` |

\* `unit_price` va `subtotal` bugalter javobida **yo'q** — ustunni shartli chizing.

**Tugmalar (status + rol):**

| Status | Tugma | Kim |
|---|---|---|
| `draft` | Yuborish → `POST /api/contracts/{id}/submit/` | sales |
| `pending_bugalter` | Tasdiqlash / Rad etish | bugalter |
| `pending_admin` | Tasdiqlash / Rad etish | admin |
| `approved` | To'lovni tasdiqlash → `POST /api/contracts/{id}/confirm-payment/` | bugalter |
| `active` | Qo'shimcha to'lov | bugalter |

To'lov formasi: `amount` (default `prepayment_amount`), `method` (`cash`/`card`/`transfer`).

### 2.4 Yangi shartnoma

```json
POST /contracts/
{
  "client": 3,
  "configuration": 12,
  "total_amount": "500000000",
  "term_days": 90,
  "signed_at": "2026-08-27",
  "items": [{ "product": 1, "quantity": 1, "unit_price": "500000000" }]
}
```

- `total_amount` bo'sh → qatorlardan hisoblanadi
- `prepayment_percent` bo'sh → 30% yoki 15% avtomatik, formada ko'rsatib tahrirlashga ruxsat bering
- Client bo'lmasa — shu yerdan "Yangi mijoz" modali ochilsin

---

## 3. To'ldirish — Buyurtmachi moduli (yangi)

### 3.1 Yetishmayotgan mahsulotlar

**Endpoint:** `GET /replenishments/low-stock/?warehouse=1`

```json
[{ "id": 5, "sku": "GPU-32", "name": "GPU 32", "total_stock": "0.00",
   "reorder_level": 10, "needed": 10, "cost_price": "400000.00" }]
```

Tepada tugma: **"Hisob shakllantirish"** → `POST /replenishments/from-low-stock/`
`{"supplier": "Etuf MCHJ"}` → yaratilgan hisob kartasiga o'ting
(`warehouse` yuborish shart emas — tizimda bitta ombor, backend o'zi oladi).

### 3.2 To'ldirish hisobi kartasi

**Endpoint:** `GET /replenishments/{id}/`

| Blok | Maydonlar |
|---|---|
| Shapka | `number`, `status_display`, `warehouse_name`, `supplier`, `expected_at` |
| Qatorlar | `items[]`: `product_name`, `quantity`, `unit_price`, `subtotal`, `supplier`, `needs_price` |
| Xarajatlar | `logistics_cost`, `other_cost` (buyurtmachi kiritadi) |
| Moliya | `items_total`, `total_amount`, `cash_available`, `shortfall`, `paid_amount` |
| Qarz | `debt`, `debt_days_left`, `debt_color` |
| Bosqichlar | `events[]`: `stage_display`, `comment`, `happened_at` |
| Tasdiqlar | `approvals[]` |

**Tugmalar:**

| Status | Tugma | Kim |
|---|---|---|
| `draft` / `rejected` | Qator qo'shish, narx kiritish, **Yuborish** → `POST /api/contracts/{id}/submit/` | buyurtmachi |
| `pending_bugalter` | Tekshirdim → `POST /api/replenishments/{id}/approve/` · Qaytarish → `POST /api/replenishments/{id}/reject/` | bugalter |
| `pending_admin` | Tasdiqlash / Rad etish, **miqdorni o'zgartirish va pozitsiya o'chirish** | admin |
| `approved` | **To'lash** → `POST /api/replenishments/{id}/pay/` | bugalter |
| `ordered` va keyin | Bosqich qo'shish → `POST /api/replenishments/{id}/events/` · **Omborga kirim** → `POST /api/replenishments/{id}/receive/` | buyurtmachi / bugalter |

**Admin tahriri:** `PATCH /replenishment-items/{id}/ {"quantity": "3"}`,
`DELETE /replenishment-items/{id}/`. Buyurtmachi buni faqat `draft`/`rejected` da qila oladi
(aks holda `403` va tushuntiruvchi matn keladi).

### 3.3 To'lov oynasi (eng muhim ekran)

`status = approved` bo'lganda bugalterga ko'rsatiladi:

```
Jami:            1 400 000
Kassada bor:       500 000
Yetmayapti:        900 000   ← qizil
[ ] Yetmagan qismni qarzga o'tqazish (60 kun)
                      [ To'lash ]
```

```json
POST /replenishments/{id}/pay/
{ "debt_amount": "900000" }
```

`debt_amount` yuborilmasa backend `shortfall` ni o'zi oladi.
Kassada pul yetmasa va qarz belgilanmasa — `400` + `suggested_debt` qaytadi.

### 3.4 Yetkazib berish kuzatuvi

`POST /replenishments/{id}/events/` — `stage`: `ordered`, `shipped`, `customs`, `cleared`, `arrived`, `note`

Timeline ko'rinishi: `GET /replenishments/{id}/timeline/` → `events[]` + `debt` bloki
(`amount`, `deadline`, `days_left`, `color`, `points[]`).

---

## 3.5 Zayavkalar — Sales ↔ Engineer (yangi)

**Sales oynasi:** "Yangi zayavka" — client (select) + **bazaviy model**
(`GET /products/?kind=machine` dan select) + ombor + matn (textarea):
`POST /configuration-requests/` (`client`, `base_product`, `warehouse`, `text`).
Ro'yxatda: `number`, `client_name`, `base_product_name`, `status_display`,
`configuration_number` (tayyor bo'lsa havola). Yaratilganda engineerlarga
notification tushadi.

**Engineer oynasi:** `?status=new` ro'yxati → **Ishga olish** (`POST /{id}/take/`) —
backend chernovik konfiguratsiyani zavod tarkibi bilan **o'zi ochadi** va javobda
`configuration` id qaytaradi → shu id bilan configurator sahifasiga o'ting →
tayyorlagach **Salesga qaytarish** (`POST /{id}/complete/` `{configuration: id}`)
— ACT'siz, chernovik holida. ACT va yakunlash sales bosqichida (§4.3).
Zayavkada model tanlanmagan bo'lsa `take` tanasida yuboriladi:
`{"base_product": id, "warehouse": id, "mode": "build|modify"}`; butunlay
modelsiz `take` — 400.

Sales'ga eslatma tushadi; `done` zayavkada "Shartnoma tuzish" tugmasi —
`configuration` bilan `POST /contracts/` ga o'tadi.

---

## 4. Configurator

> **Kim ishlaydi:** yozish — faqat **Engineer** (va admin). Sales bu bo'limda
> faqat ko'radi; uning ishi zayavka yuborish (§3.5).

### 4.1 Konfiguratsiya yig'ish

1. **Bazaviy model** tanlanadi — `GET /products/?kind=machine`
   Javobdagi `specs[]` zavod tarkibini beradi (`component_name`, `quantity`, `component_stock`)
2. `POST /configurations/` — **`items` yubormasangiz zavod tarkibi avtomatik yuklanadi**,
   javob darrov to'liq qatorlar bilan qaytadi; foydalanuvchi keyin keraklisini o'zgartiradi

```json
{
  "base_product": 1, "client": 3, "warehouse": 1,
  "items": [
    { "component": 7, "label": "SSD", "quantity": 1 },
    { "component": 9, "label": "GPU", "quantity": 1, "unit_price": "4500000" }
  ]
}
```

`unit_price` yuborilmasa — ombordagi narx avtomatik qo'yiladi.

### 4.2 Konfiguratsiya kartasi

| Element | Manba |
|---|---|
| Qatorlar jadvali | `items[]`: `component_name`, `quantity`, `unit_price`, `stock_price`, `needs_price`, `available`, `shortage`, `source` |
| "Omborda bor / Kirim kerak" belgisi | `source` = `stock` / `purchase` |
| Narx yo'q ogohlantirishi | `needs_price: true` → qizil qator, inline narx kiritish |
| Tayyor variant banneri | `ready_variant: {sku, name, price, stock, is_base_model}` → "Omborda tayyor: HP 880 — 25 000 000 (3 dona)". `is_base_model: true` — tarkib o'zgartirilmagan, bazaviy modelning o'zi |
| Jami | `items_total` (qatorlar) va `total_price` (tayyor variant narxi bo'lsa — o'sha) |
| ACT | `act` select (`GET /acts/?is_active=true`) |

**Tugmalar:** Ombor tekshiruvi (`GET /api/configurations/{id}/stock-check/`), **Yakunlash**
(`POST /api/configurations/{id}/finalize/`), Excel (`GET /api/configurations/{id}/export-excel/`),
Buyurtmaga biriktirish (`POST /api/configurations/{id}/attach/`).

`Yakunlash` — **sales oynasida** (engineer'da bu tugma bo'lmaydi, 403):
ACT tanlangan (yoki tanada `{"act": id}` yuboriladi) **va** `needs_price: true`
qator yo'q bo'lsa faol. Sales ACT ni o'zi yaratadi (`POST /acts/`), yakunlagach
shartnoma tuzib bugalterga yuboradi.
Xato javobi narxi yo'q butlovchilar ro'yxatini beradi:

```json
{ "detail": "Narxi kiritilmagan butlovchilar bor.", "items": ["RAM 4"] }
```

Yakunlangach `variant_sku` paydo bo'ladi — bu ombordagi yangi tayyor pozitsiya.

---

### 4.3 Tayyor mahsulotni o'zgartirish (modify rejimi)

Yangi konfiguratsiya oynasida rejim tanlovi:

- **Yig'ish** (`build`) — hozirgi oqim, reja
- **Tayyorini o'zgartirish** (`modify`) — omborda butun mahsulot bor bo'lganda

Modify oqimi:

1. `POST /configurations/` — `mode: "modify"` bilan; tarkib avtomatik yuklanadi
2. Foydalanuvchi qatorlarni o'zgartiradi (RAM 4 o'chirildi, RAM 8 qo'shildi)
3. `GET /configurations/{id}/changes/` — ikki ro'yxat ko'rsatiladi:
   **Qo'shiladi** (ombordan olinadi, `available` bilan) va
   **Yechib olinadi** (omborga qaytadi, `unit_price` tahrirlanadigan input)
4. `POST /finalize/` — `{"removals": {"<component_id>": "<narx>"}}` bilan
5. Muvaffaqiyatda: ombor harakatlari bo'ladi, `removals[]` tarixda qoladi,
   bugalterga eslatma tushadi

Xato holatlari: tayyor mahsulot omborda yo'q — `400` (matni bilan);
qo'shiladigan qism yetmaydi — `400` + `items[]` ro'yxati.

---

## 5. Ombor

**Bu bo'lim faqat ko'rish uchun** — "Qo'shish / Tahrirlash" tugmalari bo'lmaydi.

| Ekran | Endpoint | Izoh |
|---|---|---|
| Mahsulotlar | `GET /products/` | filtr: `kind`, `is_active`, `base_model`; `total_stock`, `is_low_stock` |
| Mahsulot kartasi | `GET /products/{id}/` | `specs[]` — tarkibi; `base_model` bo'lsa "variant" belgisi |
| Qoldiqlar | `GET /stocks/` | filtr: `product`, `warehouse` |
| Harakatlar tarixi | `GET /movements/` | filtr: `type`, `reason`, `warehouse` |
| Omborlar | `GET /warehouses/` | |

**Yangi mahsulot qayerdan qo'shiladi:** Buyurtmachining to'ldirish buyurtmasida —
qator qo'shishda `product` o'rniga `product_name` yozilsa, mahsulot katalogga tushadi
(§3.2 ga qarang). Configurator ham yakunlanganda yangi variant qo'shadi.

---

## 6. Kirim (Purchases)

| Ekran | Endpoint |
|---|---|
| Ro'yxat | `GET /purchases/` · filtr `?type=local|import|ustav`, `?status=` |
| Karta | `GET /purchases/{id}/` — `items[]`, `documents[]`, `customs_duty`, `tax_amount`, `total_amount` |
| Hujjat yuklash | `POST /purchase-documents/` (multipart) — bugalter; `kind`: shartnoma / invoys / bojxona / boshqa |
| Yo'ldagilar | `GET /purchases/in-transit/` |
| Import grafigi | `GET /purchases/{id}/timeline/` |
| Qabul qilish | `POST /purchases/{id}/receive/` (bugalter/admin) |

Import formasi: `lead_days`, `ordered_at` → `expected_at` avtomatik hisoblanadi.
USTAV turida `customs_duty` va `tax_amount` maydonlari ko'rsatiladi.

---

## 7. Kassa

### 7.1 Umumiy hisobot

`GET /cash-transactions/summary/` → `income_total`, `expense_total`, `balance`, `by_category[]`

Filtrlar bilan birga ishlaydi: `?occurred_at__gte=...` (sana oralig'i uchun `ordering` va
`page` bilan birga qo'llang).

### 7.2 Harakatlar

`GET /cash-transactions/` — ustunlar: `occurred_at`, `direction_display`, `category_name`,
`amount`, `currency`, manba havolasi (`contract` / `purchase` / `loan` / `expense_request`).

### 7.3 Yacheykalar

`GET /cash-categories/` · `POST` bilan yangi kichik xarajat turi qo'shiladi
(`code`, `name`, `direction`). Tizim yacheykalari `is_system: true` — o'chirilmasin.

### 7.4 Qarzlar

`GET /loans/` · filtr `?status=active`, `?source=personal|supplier`

Ustunlar: `lender_name`, `amount`, `repaid`, `balance`, `deadline`, `days_left`, `color`,
`source_display`. Tugma: `POST /loans/{id}/repay/` (`amount` ixtiyoriy — bo'sh bo'lsa to'liq).

`source=supplier` — Buyurtmachi hisobidan kelib chiqqan qarz.

### 7.5 Xarajat so'rovlari

| Rol | Ko'rinish |
|---|---|
| bugalter | `POST /expense-requests/` — kategoriya, summa, maqsad |
| admin | ro'yxatda `pending` lar + **Ruxsat berish** / **Rad etish** |

Admin `approve` qilgach kassaga chiqim avtomatik yoziladi.

---

## 8. Mijozlar

| Ekran | Endpoint |
|---|---|
| Ro'yxat | `GET /clients/` · filtr `?type=individual|legal` · qidiruv (`name`, `phone`, `inn`, `passport`) |
| Karta | `GET /clients/{id}/` — `display_name`, `order_count` o'rniga shartnomalar ro'yxati |
| Qo'shish | `POST /clients/` (sales, buyurtmachi, admin) |

Forma maydonlari turga qarab almashadi — [09-FRONTEND-REACT.md §7](09-FRONTEND-REACT.md).

---

## 9. ACT

`GET /acts/` — hamma ko'radi. `POST/PATCH/DELETE` — **faqat admin**.

Maydonlar: `number`, `title`, `description`, `issued_at`, `file` (yuklash), `is_active`.

Fayl yuborish `multipart/form-data` bilan.

---

## 10. Foydalanuvchilar va audit (faqat admin)

| Ekran | Endpoint |
|---|---|
| Foydalanuvchilar | `GET/POST /users/` · filtr `?role=`, `?is_active=` |
| Yangi foydalanuvchi | `POST /users/` — `username`, `password`, `role`, `phone`, `language` |
| Audit | `GET /activity-logs/` · filtr `?user=`, `?action=`, `?entity=` |

Audit ustunlari: `created_at`, `user_name`, `action_display`, `entity`, `object_id`, `description`.

---

## 11. Ekranlar ro'yxati (qisqacha)

| # | Ekran | Asosiy endpoint |
|---|---|---|
| 1 | Login | `POST /auth/login/` |
| 2 | Dashboard | `GET /dashboard/` |
| 3 | Leads (kanban) | `/leads/` |
| 4 | Shartnomalar ro'yxati | `/contracts/` |
| 5 | Shartnoma kartasi | `/contracts/{id}/` va `/contracts/{id}/timeline/` |
| 6 | Yetishmayotgan mahsulotlar | `/replenishments/low-stock/` |
| 7 | To'ldirish hisoblari | `/replenishments/` |
| 8 | To'ldirish kartasi + to'lov | `/replenishments/{id}/` va `/replenishments/{id}/pay/` |
| 9 | Yetkazib berish kuzatuvi | `/replenishments/{id}/timeline/` |
| 10 | Configurator | `/configurations/` |
| 11 | Konfiguratsiya kartasi | `/configurations/{id}/` va `/configurations/{id}/stock-check/` |
| 12 | Mahsulotlar / qoldiq / harakat | `/products/`, `/stocks/`, `/movements/` |
| 13 | Kirim ro'yxati va kartasi | `/purchases/` |
| 14 | Kassa hisoboti | `/cash-transactions/summary/` |
| 15 | Qarzlar | `/loans/` |
| 16 | Xarajat so'rovlari | `/expense-requests/` |
| 17 | Mijozlar | `/clients/` |
| 18 | ACT | `/acts/` |
| 19 | Foydalanuvchilar | `/users/` |
| 20 | Audit | `/activity-logs/` |

---

## 12. Yordamchi endpointlar

Bular alohida ekran emas — yuqoridagi sahifalar ichida ishlatiladi.

| Endpoint | Qayerda kerak | Metodlar |
|---|---|---|
| `/api/contract-items/` | Shartnoma kartasi — qatorni alohida qo'shish/tahrirlash | GET, POST, PATCH, DELETE |
| `/api/contract-payments/` | Shartnoma kartasi — to'lovlar ro'yxati | GET, POST (bugalter) |
| `/api/contract-approvals/` | Shartnoma kartasi — tasdiqlash tarixi | GET |
| `/api/configuration-items/` | Configurator — qatorni alohida tahrirlash | GET, POST, PATCH, DELETE |
| `/api/product-specs/` | Mahsulot kartasi — zavod tarkibi | GET |
| `/api/purchase-items/` | Kirim kartasi — qatorlar | GET, POST, PATCH, DELETE |
| `/api/purchase-documents/` | Kirim kartasi — biriktirilgan hujjatlar (TZ 2.2) | GET, POST (bugalter), PATCH, DELETE |
| `/api/replenishment-items/` | To'ldirish kartasi — qatorlar va **yangi mahsulot qo'shish** | GET, POST, PATCH, DELETE |
| `/api/replenishment-approvals/` | To'ldirish kartasi — tasdiqlash tarixi | GET |
| `/api/replenishment-events/` | To'ldirish kartasi — yetkazib berish bosqichlari | GET |
| `/api/notifications/{id}/mark-read/` | Yuqori paneldagi qo'ng'iroq | POST |

Ko'p hollarda bular kerak emas: asosiy kartalar (`/contracts/{id}/`, `/replenishments/{id}/`,
`/configurations/{id}/`) javobida `items`, `payments`, `approvals`, `events` allaqachon
ichma-ich keladi. Alohida endpointlar faqat bitta qatorni tahrirlash yoki o'chirish uchun.

---

## 13. Sinov foydalanuvchilari

Serverda `make docker-demo` ishlatilgach (parol `Ombor2026!`):

| Login | Rol |
|---|---|
| `admin` | Administrator |
| `bugalter` | Bugalter |
| `sales1`, `sales2` | Sales |
| `buyurtmachi` | Buyurtmachi |

Demo mijozlar ham yaratiladi (2 jismoniy, 2 yuridik).
