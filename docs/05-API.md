# 05 — API

Baza: `http://127.0.0.1:8000/api/`
Interaktiv hujjat: `/api/docs/` · OpenAPI: `/api/schema/`

## Autentifikatsiya (JWT)

```
POST /api/auth/login/
{"username": "sales1", "password": "parol"}

→ {"access": "...", "refresh": "..."}
```

```
POST /api/auth/refresh/
{"refresh": "..."}
```

Har bir so'rovda: `Authorization: Bearer <access>`
Access — 12 soat, refresh — 7 kun (rotatsiya yoqilgan).

## Umumiy qoidalar

| Narsa | Qanday |
|---|---|
| Sahifalash | `?page=2` (sahifada 20 ta), javob: `{count, next, previous, results}` |
| Qidiruv | `?search=matn` |
| Filtr | `?status=active&client=3` |
| Saralash | `?ordering=-created_at` |
| Xato | `400` validatsiya, `401` token yo'q, `403` rol ruxsat bermaydi, `404` topilmadi |

---

## Foydalanuvchilar

| Metod | Manzil | Kim |
|---|---|---|
| GET/POST | `/users/` | admin |
| GET/PUT/PATCH/DELETE | `/users/{id}/` | admin |
| GET | `/users/me/` | hamma |

Filtr: `role`, `is_active`. Qidiruv: `username`, `first_name`, `last_name`, `email`.

---

## Clients

| Metod | Manzil |
|---|---|
| GET/POST | `/clients/` |
| GET/PUT/PATCH/DELETE | `/clients/{id}/` |

Filtr: `type`. Qidiruv: `full_name`, `company_name`, `phone`, `inn`, `passport`, `jshshir`.

**Jismoniy shaxs:**
```json
POST /api/clients/
{
  "type": "individual",
  "full_name": "Kamronbek Rustamov",
  "passport": "AA1234567",
  "jshshir": "12345678901234",
  "phone": "+998901112233",
  "email": "mijoz@mail.uz"
}
```

**Yuridik shaxs** (TZ 2.1: MFO, bank nomi va hisob raqam majburiy, manzil ixtiyoriy)**:**
```json
POST /api/clients/
{
  "type": "legal",
  "company_name": "Ombor Servis MCHJ",
  "inn": "305123456",
  "jshshir": "98765432109876",
  "mfo": "00423",
  "bank_name": "Ipoteka Bank, Chilonzor filiali",
  "account_number": "20208000600123456001",
  "director_name": "Aziz Karimov",
  "phone": "+998901112244",
  "address": "Toshkent, Chilonzor 5"
}
```

Bugalter `POST` qilsa → `403`.

---

## Ombor

Ombor bo'limi **faqat o'qish uchun** — TZ da alohida "mahsulot qo'shish" oynasi yo'q.
Biznesda **BITTA ombor** bor (filial yo'q): ikkinchi ombor yaratib bo'lmaydi,
`GET /warehouses/` doim bitta yozuv qaytaradi. `warehouse` maydoni barcha
jarayonlarda **ixtiyoriy** — yuborilmasa yagona ombor avtomatik olinadi.

| Endpoint | Metod | Filtrlar |
|---|---|---|
| `/warehouses/` | GET | `is_active` |
| `/products/` | GET | `kind`, `is_active`, `base_model` |
| `/product-specs/` | GET/POST/PATCH/DELETE | `product`, `component` — **yozish: engineer, buyurtmachi** (tayyor model tarkibi) |
| `/stocks/` | GET | `product`, `warehouse` |
| `/movements/` | GET | `product`, `warehouse`, `type`, `reason` |

Mahsulot javobi: `sku`, `name`, `kind`, `cost_price`, `sale_price`, `stock_price`,
`reorder_level`, `total_stock`, `is_low_stock`, `base_model`, `is_variant`, `signature`, `specs[]`.

**Tayyor model tarkibini kiritish** (engineer, buyurtmachi, admin) — model kirim qilingach
ichidagi configlari shu yerda yoziladi; bazada yo'q butlovchi bo'lsa
`new_component_name` bilan katalogga qo'shiladi:

```json
POST /api/product-specs/
{"product": 21, "component": 8, "label": "SSD", "quantity": 2}
```

```json
POST /api/product-specs/
{"product": 21, "new_component_name": "Quvvat bloki 850W", "label": "PSU", "quantity": 1}
```

Takror butlovchi — 400; tarkib faqat `kind=machine` mahsulotga qo'shiladi.

**Yangi mahsulot qayerdan keladi:**

| Yo'l | Qanday |
|---|---|
| Buyurtmachi buyurtma qiladi | `POST /replenishment-items/` da `product_name` yuboriladi — mahsulot shu qator bilan katalogga tushadi (TZ 7) |
| Configurator variant yaratadi | `POST /configurations/{id}/finalize/` yangi tarkibni tayyor pozitsiya qilib qo'shadi (TZ 6.2) |

**Qoldiq qanday o'zgaradi:** faqat jarayonlar orqali — `POST /purchases/{id}/receive/`
va `POST /replenishments/{id}/receive/` (TZ 1-bo'lim: Kirim va Chiqim).

---

## Zayavkalar — Sales → Engineer

Sales client bilan gaplashib xohishni **matnda** yozadi va Engineerga yuboradi.
Engineer configuratorda tayyorlab, konfiguratsiyani zayavkaga biriktiradi
(**ACT'siz, chernovik holida**) — sales'ga eslatma boradi. Sales ACT kiritadi,
`finalize` bilan yakunlaydi va shartnoma tuzib bugalterga yuboradi.

| Metod | Manzil | Kim |
|---|---|---|
| GET | `/configuration-requests/` | hamma; filtr: `status`, `client`, `taken_by`, `configuration` |
| POST | `/configuration-requests/` | sales (admin) — engineerlarga notification tushadi |
| GET/PUT/PATCH/DELETE | `/configuration-requests/{id}/` | sales, engineer, admin |
| POST | `/configuration-requests/{id}/take/` | **engineer** — ishga oladi, chernovik konfiguratsiya avtomatik ochiladi |
| POST | `/configuration-requests/{id}/complete/` | **engineer** — konfiguratsiyani biriktiradi |

```json
POST /api/configuration-requests/
{"client": 3, "base_product": 1, "warehouse": 1,
 "text": "Client 2 ta kuchli kompyuter xohlaydi: SSD 2 TB, GPU zo'r bo'lsin."}
```

`base_product` — sales taxmin qilgan bazaviy model (ixtiyoriy, lekin `take` uchun kerak).
Yaratilgan zahoti barcha faol engineerlarga Notification boradi.

**take** — chernovik konfiguratsiyani o'zi ochadi: bazaviy model (tana > zayavkadagi),
zavod tarkibi avtomatik yuklanadi, `configuration` maydoni to'ldiriladi. Tana ixtiyoriy:

```json
POST /api/configuration-requests/7/take/
{"base_product": 1, "warehouse": 1, "mode": "build"}
```

Model hech qayerda ko'rsatilmagan bo'lsa — `400 {"base_product": "...tanlanishi shart"}`.
Komponent (`kind != machine`) tanlansa ham 400.

```json
POST /api/configuration-requests/7/complete/
{"configuration": 12}
```

Holatlar: `new` → `in_progress` (take) → `done` (complete). Raqam: `ZVK-00001`.
`complete` da sales'ga (zayavka egasiga) notification tushadi.

---

## Configurator

| Metod | Manzil | Izoh |
|---|---|---|
| GET/POST | `/acts/` | yozish **sales** (admin) — engineer tayyorlagach sales rasmiylashtiradi |
| GET/POST | `/configurations/` | **yozish: engineer (admin)**; qatorlar ixtiyoriy |
| PUT/PATCH/DELETE | `/configurations/{id}/` | faqat `draft` holatida — `ready`/`attached` 400 qaytaradi |
| GET | `/configurations/{id}/stock-check/` | omborda bor/yo'qligi |
| GET | `/configurations/{id}/changes/` | zavod tarkibiga nisbatan farq (modify rejimi uchun) |
| POST | `/configurations/{id}/finalize/` | **sales bosqichi** (engineer 403); ACT majburiy, tanada berish mumkin: `{"act": 2}`; ombor tanlanmagan bo'lsa faol ombor o'zi olinadi |
| POST | `/configurations/{id}/attach/` | kirim buyurtmasiga biriktirish |
| POST | `/configurations/{id}/request-procurement/` | **engineer** — yetishmaganlardan to'ldirish hisobi (TLD) ochib buyurtmachi/sales/bugalterga xabar beradi; hammasi omborda bo'lsa 400 |
| GET | `/configurations/{id}/export-excel/` | `.xlsx` fayl |
| GET/POST | `/configuration-items/` | qatorni alohida qo'shish — `configuration` majburiy, faqat `draft`; bazada yo'q tovar uchun `new_component_name` |
| GET/PUT/PATCH/DELETE | `/configuration-items/{id}/` | filtr: `configuration`, `component`; faqat `draft` da o'zgaradi |

Qatorni alohida qo'shish:
```json
POST /api/configuration-items/
{"configuration": 12, "component": 7, "label": "SSD qo'shimcha", "quantity": 1}
```

Bazada yo'q tovar — `component` o'rniga nom yoziladi, tovar katalogga o'zi tushadi:
```json
POST /api/configuration-items/
{"configuration": 12, "new_component_name": "RAM 32 GB", "label": "RAM",
 "quantity": 2, "unit_price": "900000"}
```

Yetishmaganlarni buyurtmachiga yuborish (javob — yaratilgan TLD hisobi):
```json
POST /api/configurations/12/request-procurement/
```

**Yaratish** (`items` ixtiyoriy — yuborilmasa zavod tarkibi avtomatik yuklanadi):
```json
POST /api/configurations/
{"base_product": 1, "client": 3, "warehouse": 1}
```

Yoki tarkibni o'zgartirib:
```json
POST /api/configurations/
{
  "base_product": 1,
  "client": 3,
  "warehouse": 1,
  "items": [
    {"component": 7, "label": "SSD", "quantity": 2},
    {"component": 9, "label": "GPU", "quantity": 1}
  ]
}
```

**Stock check javobi:**
```json
{
  "configuration": "CFG-00001",
  "ready_variant": "HP-880-V01",
  "variant_price": "5500000.00",
  "variant_stock": "3.00",
  "total_price": "5500000.00",
  "items": [
    {"component": "SSD 1 TB", "quantity": 1, "available": 5, "shortage": 0,
     "source": "stock", "unit_price": "1500000.00", "needs_price": false},
    {"component": "GPU 32", "quantity": 1, "available": 0, "shortage": 1,
     "source": "purchase", "unit_price": "0.00", "needs_price": true}
  ]
}
```

Narxlash qoidasi (TZ 6.2):

- `unit_price` yuborilmasa — ombordagi narx avtomatik qo'yiladi
- `needs_price: true` qator bo'lsa `finalize` `400` qaytaradi:
  `{"detail": "Narxi kiritilmagan butlovchilar bor.", "items": ["RAM 4"]}`
- Yakunlangach javobda `variant`, `variant_sku`, `ready_variant` to'ladi — bu ombordagi
  tayyor pozitsiya (yangi yaratilgan yoki avvaldan mavjud)
- Tarkib **o'zgartirilmagan** bo'lsa, tayyor pozitsiya bazaviy modelning o'zi bo'ladi
  (`ready_variant.is_base_model: true`) — narx va qoldiq undan olinadi

### Ikki rejim (TZ 6.2)

| `mode` | Ma'nosi |
|---|---|
| `build` (default) | Butlovchilardan yig'ish — reja; yakunlashda ombor harakati bo'lmaydi |
| `modify` | **Ombordagi tayyor mahsulot o'zgartiriladi** — yakunlashda haqiqiy ombor harakatlari |

**Farqni ko'rish:**
```json
GET /api/configurations/{id}/changes/
{
  "configuration": "CFG-00003",
  "mode": "modify",
  "added":   [{"component": 9, "name": "RAM 8 GB", "quantity": 1, "available": "3.00"}],
  "removed": [{"component": 7, "name": "RAM 4 GB", "quantity": 1, "unit_price": "400000.00"}]
}
```

**Modify rejimida yakunlash** — yechib olingan qism narxini o'zgartirish mumkin:
```json
POST /api/configurations/{id}/finalize/
{"removals": {"7": "350000"}}
```

Nima bo'ladi:
1. Ombordan **1 dona tayyor mahsulot** chiqadi (yo'q bo'lsa — `400`)
2. Qo'shilgan butlovchilar ombordan chiqadi (yetmasa — `400`, ro'yxati bilan)
3. **Yechib olinganlar omborga qaytadi** — `removals[]` da narxi bilan yozilib qoladi
4. O'zgartirilgan mahsulot (variant) omborga 1 dona kirim bo'ladi
5. **Bugalterga xabar** boradi: ACT raqami + yechib olinganlar ro'yxati

Konfiguratsiya javobida `removals[]` — yechib olingan qismlar tarixi.

**Biriktirish:**
```json
POST /api/configurations/12/attach/
{"purchase": 4}
```

---

## Kirim (Purchases)

| Metod | Manzil | Izoh |
|---|---|---|
| GET/POST | `/purchases/` | yozish: admin, bugalter |
| POST | `/purchases/{id}/receive/` | omborga kirim + kassaga chiqim |
| GET | `/purchases/{id}/timeline/` | import kunlari line chart |
| GET | `/purchases/in-transit/` | yo'ldagilar |
| GET/POST | `/purchase-items/` | |
| GET/POST | `/purchase-documents/` | hujjat yuklash — bugalter (TZ 2.2) |
| GET/PUT/PATCH/DELETE | `/purchase-documents/{id}/` | filtr: `purchase`, `kind` |

Filtr: `type`, `status`, `warehouse`, `currency`.

**Import yaratish:**
```json
POST /api/purchases/
{
  "type": "import",
  "supplier": "Shenzhen Tech Co",
  "warehouse": 1,
  "currency": "USD",
  "exchange_rate": "12800",
  "lead_days": 90,
  "ordered_at": "2026-08-27",
  "status": "in_transit",
  "customs_duty": "5000000",
  "tax_amount": "3000000",
  "items": [
    {"product": 9, "quantity": "10", "unit_price": "400"}
  ]
}
```

**Hujjat biriktirish** (TZ 2.2 — import hujjatlari, bugalter yuklaydi):
```
POST /api/purchase-documents/   (multipart/form-data)
purchase=3, kind=customs, title=Bojxona deklaratsiyasi, file=<fayl>
```

`kind`: `contract` (shartnoma), `invoice` (invoys), `customs` (bojxona deklaratsiyasi), `other`.
Kirim javobida hujjatlar `documents[]` bo'lib keladi. Sales bu bo'limni ko'rmaydi (403).

**Timeline javobi:**
```json
{
  "number": "KIR-00001",
  "type": "import",
  "status": "in_transit",
  "start_date": "2026-08-27",
  "term_days": 90,
  "deadline": "2026-11-25",
  "days_left": 90,
  "days_passed": 0,
  "color": "green",
  "is_overdue": false,
  "points": [{"date": "2026-08-27", "days_left": 90, "color": "green"}, "..."]
}
```

---

## Sotuv (Sales)

| Metod | Manzil | Kim |
|---|---|---|
| GET/POST | `/leads/` | admin, sales |
| GET/POST | `/contracts/` | admin, sales; filtr: `status`, `client`, `currency`, `configuration` |
| POST | `/contracts/{id}/submit/` | sales |
| POST | `/contracts/{id}/approve/` | bugalter → keyin admin |
| POST | `/contracts/{id}/reject/` | bugalter / admin |
| POST | `/contracts/{id}/confirm-payment/` | bugalter |
| GET | `/contracts/{id}/timeline/` | hamma |
| GET | `/contracts/deadlines/` | hamma |
| GET/POST | `/contract-items/` | admin, sales |
| GET/POST | `/contract-payments/` | admin, bugalter; POST `confirm-payment` bilan bir xil yo'ldan o'tadi: `paid_at` ixtiyoriy (default: hozir), kassaga kirim, balans yopilsa `completed` |
| GET | `/contract-approvals/` | faqat o'qish |

**Shartnoma yaratish:**
```json
POST /api/contracts/
{
  "client": 3,
  "configuration": 12,
  "total_amount": "500000000",
  "term_days": 90,
  "signed_at": "2026-08-27",
  "items": [
    {"product": 1, "quantity": 1, "unit_price": "500000000"}
  ]
}
```
`total_amount` yuborilmasa qatorlardan hisoblanadi. `prepayment_percent` bo'sh bo'lsa avtomatik 30% yoki 15%.

**Tasdiqlash:**
```json
POST /api/contracts/7/approve/
{"comment": "Bandlar to'g'ri"}
```

**To'lovni tasdiqlash** (summa yuborilmasa oldindan to'lov summasi olinadi):
```json
POST /api/contracts/7/confirm-payment/
{"amount": "150000000", "method": "transfer"}
```
Natija: `status = active`, `start_date = bugun`, kassaga `sale` kirimi tushadi,
**sotilgan mahsulotlar ombordan chiqim qilinadi** (birinchi to'lovda, TZ 9).
Omborda yetarli bo'lmasa — `400`:

```json
{"detail": "Omborda sotish uchun mahsulot yetarli emas.",
 "items": ["HP 880 (kerak: 5, omborda: 3)"]}
```

**Timeline javobi:**
```json
{
  "number": "SHT-00007",
  "status": "active",
  "total_amount": "500000000.00",
  "paid": "150000000.00",
  "balance": "350000000.00",
  "start_date": "2026-08-27",
  "term_days": 90,
  "deadline": "2026-11-25",
  "days_left": 90,
  "days_passed": 0,
  "color": "green",
  "is_overdue": false,
  "points": [{"date": "2026-08-27", "days_left": 90, "color": "green"}, "..."]
}
```

**Deadlines javobi** (dashboard uchun):
```json
[{"id": 7, "number": "SHT-00007", "client": "Ali Valiyev", "days_left": 5, "color": "red", "balance": "350000000.00"}]
```

> Eslatma: `items[].unit_price` va `items[].subtotal` faqat sales va admin javobida bo'ladi.

---

## Omborni to'ldirish — Buyurtmachi (TZ 7)

| Metod | Manzil | Kim |
|---|---|---|
| GET | `/replenishments/low-stock/?warehouse=1` | hamma |
| POST | `/replenishments/from-low-stock/` | buyurtmachi |
| GET/POST | `/replenishments/` | yozish: admin, buyurtmachi |
| GET/PUT/PATCH/DELETE | `/replenishments/{id}/` | admin, buyurtmachi |
| POST | `/replenishments/{id}/submit/` | buyurtmachi |
| POST | `/replenishments/{id}/approve/` | avval bugalter, keyin admin |
| POST | `/replenishments/{id}/reject/` | bugalter / admin |
| POST | `/replenishments/{id}/pay/` | bugalter |
| POST | `/replenishments/{id}/events/` | buyurtmachi / bugalter |
| POST | `/replenishments/{id}/receive/` | buyurtmachi / bugalter |
| GET | `/replenishments/{id}/timeline/` | hamma |
| GET/POST/PATCH/DELETE | `/replenishment-items/` | admin doim, buyurtmachi qoralamada |

**Buyurtmaga qator qo'shish = mahsulot qo'shish (TZ 7):**

```json
POST /api/replenishment-items/
{
  "replenishment": 7,
  "product_name": "RAM 16 GB",
  "product_sku": "RAM-16",
  "quantity": "5",
  "unit_price": "350000"
}
```

- `product_name` yuborilsa va bunday mahsulot bazada bo'lmasa — u **katalogga qo'shiladi**
  (`product_sku` berilmasa, `MAH-00001` ko'rinishida raqam beriladi)
- Bazada bor mahsulot uchun oddiy `"product": 5` yuboriladi
- Nomi mos keladigan mahsulot bo'lsa, dublikat yaratilmaydi
- `product` ham, `product_name` ham bo'lmasa — `400`
| GET | `/replenishment-approvals/`, `/replenishment-events/` | faqat o'qish |

**Yetishmayotganlar ro'yxati:**
```json
GET /api/replenishments/low-stock/?warehouse=1
[
  {"id": 5, "sku": "GPU-32", "name": "GPU 32", "total_stock": "0.00",
   "reorder_level": 10, "needed": 10, "cost_price": "400000.00"}
]
```

**Ro'yxatdan hisob shakllantirish:**
```json
POST /api/replenishments/from-low-stock/
{"warehouse": 1, "supplier": "Etuf MCHJ"}
```

**Hisob javobi — admin oynasi uchun muhim maydonlar:**
```json
{
  "number": "TLD-00001",
  "status": "pending_admin",
  "items_total": "1200000.00",
  "logistics_cost": "150000.00",
  "other_cost": "50000.00",
  "total_amount": "1400000.00",
  "cash_available": "500000.00",
  "shortfall": "900000.00",
  "debt": null,
  "debt_days_left": null,
  "debt_color": "grey",
  "items": [], "approvals": [], "events": []
}
```

**To'lov** — pul yetmasa farqi qarzga o'tadi:
```json
POST /api/replenishments/7/pay/
{"debt_amount": "900000"}
```

`debt_amount` yuborilmasa `shortfall` olinadi. Kassada pul yetmasa `400`:
```json
{"detail": "Kassada yetarli pul yo'q.", "total": "1400000.00",
 "cash_available": "500000.00", "suggested_debt": "900000.00"}
```

**Bosqich qo'shish** (TZ 7.3):
```json
POST /api/replenishments/7/events/
{"stage": "customs", "comment": "Bojxonada rasmiylashtirilmoqda"}
```

`stage`: `ordered`, `shipped`, `customs`, `cleared`, `arrived`, `note`.

**Omborga kirim:** `POST /api/replenishments/7/receive/` — qoldiq oshadi va qarz muddati
shu kundan **60 kun** qilib qayta hisoblanadi.

**Timeline javobi:**
```json
{
  "number": "TLD-00001",
  "status": "delivered",
  "total_amount": "1400000.00",
  "paid_amount": "500000.00",
  "events": [{"stage": "customs", "stage_display": "Bojxonada", "happened_at": "..."}],
  "debt": {"amount": "900000.00", "deadline": "2026-10-26", "days_left": 60,
           "color": "green", "points": []}
}
```

---

## Kassa (Finance)

| Metod | Manzil | Izoh |
|---|---|---|
| GET/POST | `/cash-categories/` | yangi yacheyka qo'shish |
| GET/POST | `/cash-transactions/` | |
| GET | `/cash-transactions/summary/` | kirim/chiqim hisoboti |
| GET/POST | `/loans/` | yaratilganda kirim yoziladi; filtr `?source=personal` yoki `?source=supplier` |
| POST | `/loans/{id}/repay/` | qaytarish |
| GET/POST | `/expense-requests/` | bugalter so'raydi |
| POST | `/expense-requests/{id}/approve/` | **faqat admin** |
| POST | `/expense-requests/{id}/reject/` | **faqat admin** |

**Summary javobi:**
```json
{
  "income_total": "10000000.00",
  "expense_total": "3000000.00",
  "balance": "7000000.00",
  "by_category": [
    {"direction": "in", "category__code": "sale", "category__name": "Mahsulot sotuvidan", "total": "10000000.00"},
    {"direction": "out", "category__code": "rent", "category__name": "Arenda", "total": "3000000.00"}
  ]
}
```

**Qarz:**
```json
POST /api/loans/
{"lender_name": "Bobur aka", "amount": "50000000", "taken_at": "2026-08-27", "deadline": "2026-09-26"}
```
Javobda: `days_left`, `color`, `repaid`, `balance`.

**Xarajat so'rovi:**
```json
POST /api/expense-requests/
{"category": 6, "amount": "4000000", "purpose": "Ofis arendasi"}
```
Admin `approve` qilganda kassaga chiqim avtomatik yoziladi.

---

## Dashboard, audit, eslatmalar

`GET /api/dashboard/`:

```json
{
  "kassa": {
    "income_total": "...", "expense_total": "...", "balance": "...",
    "income_by_category": [], "expense_by_category": []
  },
  "kirim": {"by_type": [{"type": "import", "count": 3}], "in_transit": 2},
  "sales": {"contracts_by_status": [], "leads_by_stage": [], "monthly_income": []},
  "clients": {"total": 12, "individual": 8, "legal": 4},
  "ombor": {"product_count": 40, "low_stock": []},
  "deadlines": [],
  "notifications": []
}
```

| Metod | Manzil | Kim |
|---|---|---|
| GET | `/activity-logs/` | faqat admin |
| GET | `/notifications/` | o'ziniki + umumiy |
| POST | `/notifications/{id}/mark-read/` | egasi |

Audit filtri: `?user=3&action=approve&entity=Contract`.
