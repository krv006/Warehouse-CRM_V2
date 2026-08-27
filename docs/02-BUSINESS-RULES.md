# 02 — Biznes qoidalari (TZ)

Bu fayl TZ dagi talablarni kodga qanday tushirilgani bilan birga ko'rsatadi.

---

## 1. Kirim (3 xil)

| Tur | Kod | Izoh |
|---|---|---|
| O'zbekiston ichidan | `local` | Omborda mahsulot bo'lmasa, UZB ichidagi yetkazib beruvchidan sotib olinadi |
| Import | `import` | Chetdan olib kelinadi, necha kunda kelishi `lead_days` da; kunlar line chart bo'lib kamayadi |
| Ustav (USTAF) | `ustav` | Bojxona va soliq bilan bog'liq: `customs_duty` va `tax_amount` maydonlari |

**Model:** `apps/purchases/models/purchase.py`

- Raqam avtomatik: `KIR-00001`
- `ordered_at` + `lead_days` → `expected_at` avtomatik hisoblanadi
- `GET /api/purchases/{id}/timeline/` — kunlar sanog'i va rang (line chart uchun)
- `GET /api/purchases/in-transit/` — yo'ldagi importlar ro'yxati
- `POST /api/purchases/{id}/receive/` — qabul qilish:
  1. har bir qator uchun `StockMovement(type=in)` yoziladi va ombor qoldigi oshadi
  2. kassaga chiqim tushadi (`import` / `contract_invoice` / `ustav_out` kategoriyasi bo'yicha)
  3. status `received`, `received_at` = bugun

Umumiy summa: `items_total + customs_duty + tax_amount`.

---

## 2. Chiqim

| Tur | Qayerda |
|---|---|
| Mijozga sotuv (so'mda) | `apps/sales` — shartnoma va to'lov |
| Import xarajati | `Purchase.receive` → kassa chiqimi |
| Ustav kapitalidan xarajat | `ustav_out` kategoriyasi |
| Kichik xarajatlar (oylik, arenda, obed, boshqa) | `ExpenseRequest` → admin ruxsati → kassa chiqimi |

**Export** (USD / EUR / CNY) — hozircha ishlamaydi, lekin joy tayyor:
`Purchase.currency`, `Contract.currency`, `CashTransaction.currency` + `exchange_rate` maydonlari
va `apps/core/choices.py` dagi `Currency` (UZS, USD, EUR, CNY).

---

## 3. Kassa

Har bir kirim va chiqim **kategoriya (yacheyka)** bo'yicha nazorat qilinadi.

### Tizim kategoriyalari (`manage.py seed_finance`)

| Kod | Nomi | Yo'nalish |
|---|---|---|
| `sale` | Mahsulot sotuvidan | kirim |
| `ustav_in` | Ustav kapitali | kirim |
| `loan` | Qarz olish | kirim |
| `import` | Import xarajati | chiqim |
| `contract_invoice` | Shartnoma fakturasi (UZB ichidan) | chiqim |
| `ustav_out` | Ustav kapitalidan xarajat | chiqim |
| `salary` | Oylik | chiqim |
| `rent` | Arenda | chiqim |
| `meal` | Obed | chiqim |
| `loan_repay` | Qarzni qaytarish | chiqim |
| `other` | Boshqa xarajat | chiqim |

Yangi yacheyka qo'shish mumkin: `POST /api/cash-categories/`.

### Hisobot

`GET /api/cash-transactions/summary/` → `income_total`, `expense_total`, `balance`, `by_category`.
Filtrlar bilan birga ishlaydi (sana, kategoriya, valyuta).

### Qarz (`Loan`)

Kimdan olindi, qancha, `deadline` qachon. Yaratilganda avtomatik **kirim** yoziladi (`loan`).
`POST /api/loans/{id}/repay/` — qaytarish (`loan_repay` chiqimi), qoldiq 0 bo'lsa status `closed`.
Muddat yaqinlashganda `check_deadlines` eslatma yaratadi.

### Bugalterning xarajati — admin ruxsati bilan

TZ: *"pul chiqazish rasxod qilishda admindan ruxsat sorash kerak boladi"*.

1. Bugalter: `POST /api/expense-requests/` (kategoriya, summa, maqsad) → status `pending`
2. Admin: `POST /api/expense-requests/{id}/approve/` → status `approved` **va** kassaga chiqim yoziladi
3. Yoki `POST /api/expense-requests/{id}/reject/` → status `rejected`, bugalterga eslatma boradi

Bugalter o'z so'rovini tasdiqlay olmaydi (403). Barcha so'rovlar hisobot sifatida saqlanadi.

---

## 4. Sales va shartnoma

### Bosqichlar

| Status | Kim harakat qiladi | Keyingi holat |
|---|---|---|
| `draft` | Sales shartnoma tuzadi | `submit` → `pending_bugalter` |
| `pending_bugalter` | Bugalter bandlarni ko'radi | `approve` → `pending_admin` |
| `pending_admin` | Admin (oxirgi etap) | `approve` → `approved` |
| `approved` | Bugalter pulni kutadi | `confirm-payment` → `active` |
| `active` | Muddat sanog'i ketmoqda | to'liq to'lansa → `completed` |
| `rejected` / `cancelled` | Rad etilgan / bekor qilingan | — |

Har bir tasdiq `ContractApproval` ga yoziladi (kim, qachon, izoh).

### Oldindan to'lov foizi

TZ: *"1 mlr dan kam bolsa 30% va undan kop bolsa 15%"*.

```python
total < 1_000_000_000  →  30%
total >= 1_000_000_000 →  15%
```

- Shartnoma saqlanganda avtomatik qo'yiladi (`prepayment_percent` bo'sh bo'lsa)
- Qo'lda o'zgartirilsa, o'zgartirilgan foiz saqlanadi
- `prepayment_amount = total_amount * percent / 100`

### Muddat sanog'i va ranglar

Sanoq **pul kelgani bugalter tomonidan tasdiqlangan kundan** boshlanadi (`start_date`).

| Holat | Rang |
|---|---|
| Boshidan muddatning 70% igacha | `green` (yashil) |
| Oxirgi 30% (lekin 10 kundan ko'p qolgan) | `yellow` (sariq) |
| **Oxirgi 10 kun va muddatdan o'tgan** | `red` (qizil) |
| Sanoq boshlanmagan | `grey` |

Qoida `apps/core/utils.py` da: `RED_ZONE_DAYS = 10`, `YELLOW_ZONE_RATIO = 0.3`.

`GET /api/contracts/{id}/timeline/` har bir kun uchun `{date, days_left, color}` qaytaradi — to'g'ridan-to'g'ri line chartga beriladi.

`GET /api/contracts/deadlines/` — faol shartnomalar, eng kam kun qolgani birinchi.

### Eslatmalar

`manage.py check_deadlines` — sariq va qizil zonadagi shartnoma, qarz va importlar uchun
`Notification` yaratadi. Takroran ishga tushirilsa dublikat yaratmaydi (idempotent).

### Narx ko'rinishi

TZ: *"Shartnomada mahsulot ni sotuv narhi korinadi sales ga faqat"*.
`ContractItem` qatoridagi `unit_price` va `subtotal` faqat **sales** va **admin** javobida bo'ladi;
bugalter javobida bu maydonlar chiqarilmaydi (shartnomaning umumiy summasi esa ko'rinadi).

### Og'zaki kelishuv (`Lead`)

Bosqichlar: `new → negotiation → verbal → contract`, yoki `lost`.
Shartnoma tuzilganda `Lead.contract` ga bog'lanadi.

---

## 5. Configurator

TZ misoli: HP 880 (SSD 512 GB, GPU 16, 4 yadro, RAM 8) → mijoz SSD 1 TB va GPU 32 xohlaydi.

1. Bazaviy modelning zavod tarkibi — `ProductSpec` (HP 880 → SSD 512 GB, GPU 16, ...).
2. `Configuration` yaratiladi: `base_product` + mijoz tanlagan `ConfigurationItem` qatorlari.
3. Har bir qator uchun avtomatik hisoblanadi:
   - `available` — omborda bor miqdor
   - `shortage` — yetishmaydigan miqdor
   - `source` = `stock` (ombordan olinadi) yoki `purchase` (kirim qilinishi kerak)
4. `GET /api/configurations/{id}/stock-check/` — shu ro'yxatni qaytaradi.
5. **ACT majburiy:** `POST /{id}/finalize/` faqat `act` biriktirilgan va qatorlari bor bo'lsa ishlaydi.
   ACT ni **faqat admin** kiritadi (`/api/acts/` yozish `IsAdminOrReadOnly` bilan yopilgan).
6. `GET /{id}/export-excel/` — chernovik Excel (butlovchi, miqdor, narx, omborda, yetishmaydi, manba, jami).
7. Tayyor bo'lsa `POST /{id}/attach/` bilan kirim buyurtmasiga biriktiriladi → status `attached`.

Configurator **barcha rollarga** ochiq (TZ: umumiy tushunchalar).

---

## 6. Client

| Jismoniy shaxs | Yuridik shaxs |
|---|---|
| F.I.SH — majburiy | Kompaniya nomi — majburiy, unique |
| Passport — majburiy, unique | INN — majburiy, unique |
| JSHSHIR — majburiy, unique | JSHSHIR — majburiy, unique |
| Telefon — majburiy, unique | Rahbar F.I.SH — majburiy |
| Email — optional | Telefon — majburiy, unique |
| Izoh — optional | Manzil — majburiy |
| | Email, izoh — optional |

Client qo'shish **bugalterda yo'q**, sales va adminda bor.

---

## 7. Audit

Har bir yaratish / o'zgartirish / o'chirish / tasdiqlash `ActivityLog` ga tushadi
(`BaseModelViewSet` avtomatik yozadi). Ro'yxat faqat adminga: `GET /api/activity-logs/`.
