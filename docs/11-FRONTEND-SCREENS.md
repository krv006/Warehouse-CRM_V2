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

| Menyu | admin | bugalter | sales | buyurtmachi |
|---|:--:|:--:|:--:|:--:|
| Dashboard | ✅ | ✅ | ✅ | ✅ |
| Sotuv (Leads, Shartnomalar) | ✅ | ✅ | ✅ | 👁 |
| To'ldirish (Buyurtmachi) | ✅ | ✅ | ⛔ | ✅ |
| Ombor | 👁 | 👁 | 👁 | 👁 |
| Configurator | ✅ | ✅ | ✅ | ✅ |
| Kirim | ✅ | ✅ | ⛔ | 👁 |
| Kassa | ✅ | ✅ | ⛔ | ⛔ |
| Mijozlar | ✅ | 👁 | ✅ | ✅ |
| ACT | ✅ | 👁 | 👁 | 👁 |
| Foydalanuvchilar | ✅ | ⛔ | ⛔ | ⛔ |
| Audit | ✅ | ⛔ | ⛔ | ⛔ |

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
| Muddat grafigi | `GET /contracts/{id}/timeline/` → `points[]` |

\* `unit_price` va `subtotal` bugalter javobida **yo'q** — ustunni shartli chizing.

**Tugmalar (status + rol):**

| Status | Tugma | Kim |
|---|---|---|
| `draft` | Yuborish → `POST /submit/` | sales |
| `pending_bugalter` | Tasdiqlash / Rad etish | bugalter |
| `pending_admin` | Tasdiqlash / Rad etish | admin |
| `approved` | To'lovni tasdiqlash → `POST /confirm-payment/` | bugalter |
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
`{"warehouse": 1, "supplier": "Etuf MCHJ"}` → yaratilgan hisob kartasiga o'ting.

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
| `draft` / `rejected` | Qator qo'shish, narx kiritish, **Yuborish** → `POST /submit/` | buyurtmachi |
| `pending_bugalter` | Tekshirdim → `POST /approve/` · Qaytarish → `POST /reject/` | bugalter |
| `pending_admin` | Tasdiqlash / Rad etish, **miqdorni o'zgartirish va pozitsiya o'chirish** | admin |
| `approved` | **To'lash** → `POST /pay/` | bugalter |
| `ordered` va keyin | Bosqich qo'shish → `POST /events/` · **Omborga kirim** → `POST /receive/` | buyurtmachi / bugalter |

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

## 4. Configurator

### 4.1 Konfiguratsiya yig'ish

1. **Bazaviy model** tanlanadi — `GET /products/?kind=machine`
   Javobdagi `specs[]` zavod tarkibini beradi (`component_name`, `quantity`, `component_stock`)
2. Foydalanuvchi tarkibni o'zgartiradi → `POST /configurations/`

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
| Tayyor variant banneri | `ready_variant: {sku, price}` → "Bu konfiguratsiya omborda bor: HP-880-V01 — 5 500 000" |
| Jami | `items_total` (qatorlar) va `total_price` (tayyor variant narxi bo'lsa — o'sha) |
| ACT | `act` select (`GET /acts/?is_active=true`) |

**Tugmalar:** Ombor tekshiruvi (`GET /stock-check/`), **Yakunlash** (`POST /finalize/`),
Excel (`GET /export-excel/`), Buyurtmaga biriktirish (`POST /attach/`).

`Yakunlash` faqat: ACT tanlangan **va** `needs_price: true` qator yo'q bo'lsa faol.
Xato javobi narxi yo'q butlovchilar ro'yxatini beradi:

```json
{ "detail": "Narxi kiritilmagan butlovchilar bor.", "items": ["RAM 4"] }
```

Yakunlangach `variant_sku` paydo bo'ladi — bu ombordagi yangi tayyor pozitsiya.

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
| Karta | `GET /purchases/{id}/` — `items[]`, `customs_duty`, `tax_amount`, `total_amount` |
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
| 5 | Shartnoma kartasi | `/contracts/{id}/` + `/timeline/` |
| 6 | Yetishmayotgan mahsulotlar | `/replenishments/low-stock/` |
| 7 | To'ldirish hisoblari | `/replenishments/` |
| 8 | To'ldirish kartasi + to'lov | `/replenishments/{id}/` + `/pay/` |
| 9 | Yetkazib berish kuzatuvi | `/replenishments/{id}/timeline/` |
| 10 | Configurator | `/configurations/` |
| 11 | Konfiguratsiya kartasi | `/configurations/{id}/` + `/stock-check/` |
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

## 12. Sinov foydalanuvchilari

Serverda `make docker-demo` ishlatilgach (parol `Ombor2026!`):

| Login | Rol |
|---|---|
| `admin` | Administrator |
| `bugalter` | Bugalter |
| `sales1`, `sales2` | Sales |
| `buyurtmachi` | Buyurtmachi |

Demo mijozlar ham yaratiladi (2 jismoniy, 2 yuridik).
