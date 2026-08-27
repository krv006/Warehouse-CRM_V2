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
6. Qoldiq to'liq yopilsa status `completed`.

Har bir tasdiq/rad `ContractApproval` ga (kim, qachon, izoh) va `ActivityLog` ga yoziladi.

### Muddat ranglari

```
90 kunlik shartnoma:
kun 0 ────────────────► kun 63 ──────────► kun 80 ─────► kun 90
      🟢 yashil              🟡 sariq          🔴 qizil
                        (oxirgi 30%)      (oxirgi 10 kun)
```

`GET /contracts/{id}/timeline/` — `points[]` ichida har bir kun uchun rang tayyor holda keladi.

---

## 2. Configurator: mijoz tarkibni o'zgartiradi

```mermaid
flowchart TD
    A[Bazaviy model: HP 880] --> B[Mijoz tarkibni o'zgartiradi]
    B --> C{Har bir butlovchi omborda bormi?}
    C -->|Ha| D[source = stock — ombordan olinadi]
    C -->|Yo'q| E[source = purchase — kirim qilinadi]
    D --> F[GET /stock-check/]
    E --> F
    F --> G{ACT biriktirilganmi?}
    G -->|Yo'q| H[finalize → 400 xato]
    G -->|Ha| I[POST /finalize/ → status ready]
    I --> J[GET /export-excel/ — chernovik]
    I --> K[POST /attach/ — kirim buyurtmasiga biriktiriladi]
    K --> L[status attached]
```

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
