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

**Yuridik shaxs:**
```json
POST /api/clients/
{
  "type": "legal",
  "company_name": "Ombor Servis MCHJ",
  "inn": "305123456",
  "jshshir": "98765432109876",
  "director_name": "Aziz Karimov",
  "address": "Toshkent, Chilonzor 5",
  "phone": "+998901112244"
}
```

Bugalter `POST` qilsa → `403`.

---

## Ombor

| Endpoint | Filtrlar |
|---|---|
| `/categories/` | `parent` |
| `/warehouses/` | `is_active` |
| `/products/` | `category`, `kind`, `unit`, `is_active` |
| `/product-specs/` | `product`, `component` |
| `/stocks/` | `product`, `warehouse` |
| `/movements/` | `product`, `warehouse`, `type`, `reason` |

`POST /movements/` qoldiqni avtomatik yangilaydi:

```json
{"product": 5, "warehouse": 1, "type": "in", "quantity": "10"}
```

`type`: `in` (kirim), `out` (chiqim), `adjust` (yakuniy qoldiqni o'rnatadi).

Mahsulot javobida `total_stock`, `is_low_stock` va `specs` bo'ladi.

---

## Configurator

| Metod | Manzil | Izoh |
|---|---|---|
| GET/POST | `/acts/` | yozish faqat admin |
| GET/POST | `/configurations/` | qatorlar (`items`) bilan birga yuboriladi |
| GET | `/configurations/{id}/stock-check/` | omborda bor/yo'qligi |
| POST | `/configurations/{id}/finalize/` | ACT majburiy |
| POST | `/configurations/{id}/attach/` | kirim buyurtmasiga biriktirish |
| GET | `/configurations/{id}/export-excel/` | `.xlsx` fayl |
| GET/POST | `/configuration-items/` | qatorni alohida qo'shish/tahrirlash |
| GET/PUT/PATCH/DELETE | `/configuration-items/{id}/` | filtr: `configuration`, `component` |

**Yaratish:**
```json
POST /api/configurations/
{
  "base_product": 1,
  "client": 3,
  "warehouse": 1,
  "items": [
    {"component": 7, "label": "SSD", "quantity": 1, "unit_price": "1500000"},
    {"component": 9, "label": "GPU", "quantity": 1, "unit_price": "4500000"}
  ]
}
```

**Stock check javobi:**
```json
{
  "configuration": "CFG-00001",
  "items": [
    {"component": "SSD 1 TB", "quantity": 1, "available": 5, "shortage": 0, "source": "stock"},
    {"component": "GPU 32", "quantity": 1, "available": 0, "shortage": 1, "source": "purchase"}
  ]
}
```

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
| GET/POST | `/contracts/` | admin, sales |
| POST | `/contracts/{id}/submit/` | sales |
| POST | `/contracts/{id}/approve/` | bugalter → keyin admin |
| POST | `/contracts/{id}/reject/` | bugalter / admin |
| POST | `/contracts/{id}/confirm-payment/` | bugalter |
| GET | `/contracts/{id}/timeline/` | hamma |
| GET | `/contracts/deadlines/` | hamma |
| GET/POST | `/contract-items/` | admin, sales |
| GET/POST | `/contract-payments/` | admin, bugalter |
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
Natija: `status = active`, `start_date = bugun`, kassaga `sale` kirimi tushadi.

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

## Kassa (Finance)

| Metod | Manzil | Izoh |
|---|---|---|
| GET/POST | `/cash-categories/` | yangi yacheyka qo'shish |
| GET/POST | `/cash-transactions/` | |
| GET | `/cash-transactions/summary/` | kirim/chiqim hisoboti |
| GET/POST | `/loans/` | yaratilganda kirim yoziladi |
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
