# 06 — Jarayonlar (workflow)

## 1. Shartnoma: sales → bugalter → admin → pul

```mermaid
stateDiagram-v2
    [*] --> draft: Sales shartnoma tuzadi
    draft --> pending_bugalter: POST /submit/ (sales)
    pending_bugalter --> pending_admin: POST /approve/ (bugalter)
    pending_bugalter --> rejected: POST /reject/ (bugalter)
    pending_admin --> approved: POST /approve/ (admin)
    pending_admin --> rejected: POST /reject/ (admin)
    approved --> active: POST /confirm-payment/ (bugalter)
    active --> active: qo'shimcha to'lovlar
    active --> completed: qoldiq = 0
    rejected --> [*]
    completed --> [*]
```

Qadamlar:

1. **Sales** clientni tanlaydi (bo'lmasa `POST /clients/` bilan qo'shadi), kerak bo'lsa configurator qiladi,
   `POST /contracts/` bilan shartnoma tuzadi. Sotuv narxi shu bosqichda ko'rinadi.
2. `POST /contracts/{id}/submit/` — shartnoma bugalterga tushadi.
3. **Bugalter** bandlarni ko'rib `approve` qiladi → admin bosqichiga o'tadi.
4. **Admin** oxirgi etap sifatida `approve` qiladi → status `approved`, eslatma yaratiladi:
   *"Oldindan to'lov 30% — 150 000 000 UZS. Pul kutilmoqda."*
5. **Bugalter** pul kelganini `confirm-payment` bilan tasdiqlaydi:
   - `ContractPayment` yoziladi
   - kassaga `sale` kirimi tushadi
   - `start_date = bugun`, status `active` — **shu kundan kunlar sanog'i boshlanadi**
   - **sotilgan mahsulotlar ombordan chiqim qilinadi** (yetmasa to'lov bloklanadi)
6. Qoldiq to'liq yopilsa status `completed`.

Har bir tasdiq/rad `ContractApproval` ga (kim, qachon, izoh) va `ActivityLog` ga yoziladi.

### Muddat ranglari

```
90 kunlik shartnoma (TZ 5.3):
qolgan kun:  90 ─────────────── 31 │ 30 ────────── 11 │ 10 ──────── 0
             🟢 yashil            │ 🟡 sariq        │ 🔴 qizil
                                  (oxirgi 1/3)       (oxirgi 10 kun)
```

`GET /contracts/{id}/timeline/` — `points[]` ichida har bir kun uchun rang tayyor holda keladi.

---

## 1.1 Omborni to'ldirish (Buyurtmachi) — TZ 7

```mermaid
stateDiagram-v2
    [*] --> draft: Yetishmayotganlar ro'yxatidan hisob
    draft --> pending_bugalter: POST /submit/ (buyurtmachi)
    pending_bugalter --> pending_admin: POST /approve/ (bugalter)
    pending_bugalter --> rejected: POST /reject/
    pending_admin --> approved: POST /approve/ (admin)
    pending_admin --> rejected: POST /reject/
    approved --> ordered: POST /pay/ (bugalter)
    ordered --> in_transit: events: shipped
    in_transit --> customs: events: customs
    customs --> in_transit: events: cleared
    in_transit --> delivered: POST /receive/
    rejected --> draft: buyurtmachi tuzatadi
    delivered --> [*]
```

Qadamlar:

1. **Buyurtmachi** `GET /replenishments/low-stock/` bilan yetishmayotganlarni ko'radi va
   `POST /replenishments/from-low-stock/` bilan hisob shakllantiradi
2. Har bir pozitsiyaga ta'minotchi narxini, so'ng `logistics_cost` va `other_cost` ni kiritadi
3. `POST /submit/` → **Bugalter** tekshiradi (`approve`) yoki qaytaradi (`reject`)
4. **Admin** ko'rib chiqadi: miqdorni o'zgartiradi, pozitsiya o'chiradi, so'ng tasdiqlaydi.
   Oynada `total_amount` va `cash_available` yonma-yon turadi
5. **Bugalter** `POST /pay/` qiladi:
   - pul yetsa → to'liq kassadan chiqim
   - yetmasa → farqi (`shortfall`) **qarzga** o'tadi (`Loan.source = supplier`)
6. Yetkazib berish bosqichlari `POST /events/` bilan qayd etiladi (bojxona va h.k.)
7. `POST /receive/` → ombor qoldig'i oshadi, **qarz muddati shu kundan 60 kun** bo'lib qayta hisoblanadi

### Pul yetmagan holat (TZ 7.1 misoli)

```
Jami:          1 400 000
Kassada:         500 000
Yetmayapti:      900 000  →  Loan(source=supplier, deadline = kirim + 60 kun)
```

## 2. Configurator: mijoz tarkibni o'zgartiradi

```mermaid
flowchart TD
    A[Bazaviy model: HP 880] --> B[Mijoz tarkibni o'zgartiradi]
    B --> S{Xuddi shu tarkib omborda bormi?}
    S -->|Ha| S1[Tayyor variant topildi — ombordagi narx qo'llanadi]
    S -->|Yo'q| C{Har bir butlovchi omborda bormi?}
    C -->|Bor, narxi ham bor| D[Narx ombordan avtomatik olinadi]
    C -->|Bor, narxi yo'q| P[needs_price — foydalanuvchi kiritadi]
    C -->|Yo'q| E[source = purchase — kirim qilinadi]
    D --> F[GET /stock-check/]
    P --> F
    E --> F
    S1 --> F
    F --> G{ACT bormi va hamma narx kiritilganmi?}
    G -->|Yo'q| H[finalize → 400 xato]
    G -->|Ha| I[POST /finalize/ → status ready]
    I --> V[Variant omborga qo'shiladi: HP-880-V01]
    I --> J[GET /export-excel/ — chernovik]
    I --> K[POST /attach/ — kirim buyurtmasiga biriktiriladi]
```

Narxlash qoidalari (TZ 6.2):

| Holat | Tizim nima qiladi |
|---|---|
| Butlovchi omborda bor, narxi bor | Narx avtomatik olinadi (`unit_price` bo'sh yuborilsa) |
| Omborda bor, narxi yo'q | `needs_price: true` — narx kiritilmaguncha yakunlanmaydi |
| Omborda yo'q | `source: purchase` — kirim qilish kerakligi belgilanadi |
| Aynan shu tarkib avval yig'ilgan | Tayyor variant (`ready_variant`) va uning ombordagi narxi qo'llanadi |

Tarkib **imzo (signature)** bilan saqlanadi — komponentlar tartibi muhim emas,
bir xil kombinatsiya doim bir xil imzo beradi.

- ACT ni **faqat admin** kiritadi (`POST /acts/`).
- Excel chernovik: butlovchi, belgi, miqdor, narx, summa, omborda, yetishmaydi, manba va jami.
- Configurator barcha rollarga ochiq.

---

## 3. Kirim (Purchase) qabul qilish

```mermaid
sequenceDiagram
    participant B as Bugalter
    participant P as Purchase API
    participant I as Inventory
    participant K as Kassa
    B->>P: POST /purchases/ (type, items, lead_days)
    Note over P: number = KIR-00001<br/>expected_at = ordered_at + lead_days
    B->>P: POST /purchases/{id}/receive/
    P->>I: har bir qator uchun StockMovement(in)
    I-->>P: Stock qoldigi oshdi
    P->>K: CashTransaction(out)
    Note over K: import / contract_invoice / ustav_out
    P-->>B: status = received, received_at = bugun
```

Ikkinchi marta `receive` qilinsa `400` qaytadi.

Import kunlari: `GET /purchases/{id}/timeline/` — shartnomadagi kabi rangli line chart.

---

## 4. Kassa: bugalterning xarajati admin ruxsati bilan

```mermaid
sequenceDiagram
    participant B as Bugalter
    participant A as Admin
    participant K as Kassa
    B->>K: POST /expense-requests/ (kategoriya, summa, maqsad)
    Note over K: status = pending
    B--xK: POST /approve/ → 403 (o'zi tasdiqlay olmaydi)
    A->>K: POST /expense-requests/{id}/approve/
    K->>K: CashTransaction(out) yoziladi
    Note over K: status = approved, decided_by = admin
    A->>K: yoki POST /reject/ → bugalterga eslatma
```

---

## 5. Kunlik eslatmalar

```bash
.venv/Scripts/python.exe manage.py check_deadlines
```

Nima qiladi:

| Manba | Shart | Eslatma darajasi |
|---|---|---|
| `Contract` (`active`) | rang `yellow` | `warning` |
| `Contract` (`active`) | rang `red` (oxirgi 10 kun yoki o'tib ketgan) | `danger` |
| `Loan` (`active`) | 10 kun va undan kam qolgan | `warning` / `danger` |
| `Purchase` (`ordered`, `in_transit`) | muddat yaqinlashgan | `warning` / `danger` |

Bir xil obyekt + muddat uchun o'qilmagan eslatma allaqachon bo'lsa, yangisi yaratilmaydi.

Windows Task Scheduler uchun kunlik komanda:

```bash
C:\Users\user\PycharmProjects\Warehouse_CRM_V2\.venv\Scripts\python.exe C:\Users\user\PycharmProjects\Warehouse_CRM_V2\manage.py check_deadlines
```

---

## 6. Og'zaki kelishuvdan shartnomagacha

```mermaid
flowchart LR
    N[new] --> NEG[negotiation]
    NEG --> V[verbal — og'zaki kelishuv]
    V --> C[contract — shartnoma tuzildi]
    NEG --> L[lost]
    V --> L
```

`Lead.contract` maydoni orqali qaysi shartnomaga aylangani ko'rinadi;
`GET /api/dashboard/` da `leads_by_stage` bo'lib chiqadi.
