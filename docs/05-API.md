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
### Bron (§11.4) — `Jami = Band + Rejada + Erkin`

Mahsulot javobida to'rt raqam: `total_stock` (jami), `reserved_hard` (Band —
shartnomalar), `reserved_soft` (Rejada — konfiguratsiyalar), `sellable_stock`
(Erkin — sotuvga ochiq), `plannable_stock` (Rejadan keyin — yangi reja uchun).

- Shartnoma tuzilganda mahsulot **qattiq** bron qilinadi (qoldiq o'zgarmaydi,
  boshqa shartnoma ololmaydi); yetmasa bor qismi band bo'ladi — tuzish
  to'silmaydi. To'lovda bron chiqimga aylanadi, reject'da bo'shaydi.
- Konfiguratsiya chernovigi **yumshoq** bron qo'yadi — hech kimni to'smaydi,
  faqat "Rejada" deb ko'rinadi. `finalize`da shartnoma broniga aylanadi.
- Muddatlar admin sozlamasida (`/company/`): `contract_reservation_days` (7),
  `configuration_reservation_days` (14); muddati o'tganini `check_deadlines`
  bo'shatadi va egasiga xabar beradi. Qo'lda bo'shatish: `POST
  /reservations/{id}/release/` — faqat admin, sabab auditga tushadi.
- Konfiguratsiya qatoridagi `available` endi **rejadan keyingi** raqam
  (o'z rejasi hisobga olinmaydi); xom qoldiq — `stock_total`.

`GET /warehouses/` doim bitta yozuv qaytaradi. `warehouse` maydoni barcha
jarayonlarda **ixtiyoriy** — yuborilmasa yagona ombor avtomatik olinadi.

| Endpoint | Metod | Filtrlar |
|---|---|---|
| `/warehouses/` | GET | `is_active` |
| `/products/` | GET, **PATCH** (§10.2: admin/bugalter — `sale_price`, `cost_price`, `reorder_level`, `is_active`) | `kind`, `is_active`, `base_model` |
| `/reservations/` | GET; `POST {id}/release/` (admin, `note` majburiy) | `product`, `kind` (`soft`/`hard`), `status`, `contract`, `configuration` |
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
| ~~complete~~ | — olib tashlandi (#4): endi engineer konfiguratsiyani `submit` qiladi, zayavka sales `approve`sida `done` bo'ladi |
| GET | `/configuration-requests/{id}/roadmap/` | B8: **zanjir ko'zgusi** — 18 qadam, uch kirish nuqtasi bir xil javob; barcha rollar to'liq ko'radi, **pul yo'q**; `label`/`state`/`tone`/`waiting_days`/`deadline`/`can_open`/`repeats`/`current_key` tayyor keladi |
| GET | `/configurations/{id}/roadmap/` | B8: xuddi shu roadmap — konfiguratsiya tomonidan |
| GET | `/contracts/{id}/roadmap/` | B8: xuddi shu roadmap — shartnoma tomonidan |
| POST | `/configurations/{id}/ask-sales/` | 9-to'plam §1B: **engineer** yarim yo'lda sales'dan aniqlashtirish so'raydi (`comment` majburiy) — `draft` → `pending_clarification`; tarkib ham, BRON ham joyida qoladi; tarixga `approvals` (step `engineer`, decision `question`), zayavka egasiga eslatma |
| POST | `/configurations/{id}/answer/` | 9-to'plam §1B: **sales** javob beradi (`comment` majburiy) — `pending_clarification` → `draft`; tarixga (step `sales`, decision `answer`), engineerga eslatma; approvals ro'yxati ikki tomonlama suhbatga aylanadi |
| POST | `/configuration-requests/{id}/reject/` | B15/9-§1A: **engineer** FAQAT `new` zayavkani izoh bilan qaytaradi (ishga olinganida 400 — `ask-sales` yoki `release` bor); `returned` — faqat sales'da (hovuzdan chiqadi) |
| POST | `/configuration-requests/{id}/release/` | 9-to'plam §2: **zayavkani olgan engineer** (admin) ishni hovuzga qaytaradi (`comment` majburiy) — muammo zayavkada emas, engineerda (vaqti yo'q); `in_progress` → `new`, CFG bekor (`cancel_reason`), bron bo'shaydi, hovuz + sales xabar oladi; SLA noldan boshlanadi |
| POST | `/configuration-requests/{id}/resend/` | B15: **sales (egasi)** tuzatib qayta yuboradi — `returned` → `new`, engineerlar hovuziga qaytadi |
| POST | `/configuration-requests/{id}/cancel/` | B17: zanjirni bekor qilish — eng ko'p ishlatiladigan kirish nuqtasi (shartnoma hali ochilmagan payt) |
| POST | `/configurations/{id}/cancel/` | B12: zanjirni bekor qilish (sales egasi / admin) |
| POST | `/contracts/{id}/cancel/` | B12: zanjirni bekor qilish; **pul qabul qilingan bo'lsa 400** |
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

## Menga taqalgan ish (EGALIK §2)

| Metod | Manzil | Izoh |
|---|---|---|
| GET | `/my-work/` | bosh sahifa navbati: `{counts, items}` — rol bo'yicha "mendan amal kutilmoqda" ro'yxati |
| GET | `/sidebar-counts/` | yon panel hisoblagichi: faqat sonlar; `/my-work/` `counts` bilan aynan bir xil (bitta funksiya) |

`items[]` qatori: `{section, entity, id, number, reason, amount, currency,
level}`. Havolani front `entity`+`id` dan quradi, ko'rsatma matnini `reason`
kodidan yozadi (`send_to_didox`, `didox_confirm`, `awaiting_payment`, `client_approval`,
`draft_to_submit`, `fix_and_resubmit`, `contact_due`, `take_request`,
`configure`, `assemble`, `track_delivery`, `decide_expense`, `loan_due`,
`awaiting_admin_approve`, `awaiting_client_payment`, `awaiting_check`,
`in_progress`). `level`: `info`/`warning`/`danger` — danger birinchi turadi.
Bo'lim kalitlari: `contracts`, `leads`, `requests`, `configurations`,
`replenishments`, `low_stock`, `expense_requests`, `loans`; 0 bo'lsa badge
chizilmaydi. Ruxsat: istalgan login — javob so'rovchi roli bo'yicha.

**SLA (TOPSHIRIQ #3):** muddatidan ortiq turgan ishning o'z qatori
`level: "danger"` + `waiting_days` (ish kunlari) bilan keladi; adminga
qo'shimcha `reason: "stale"` qatorlari `holder_role`/`holder_name` bilan —
kimda turib qolgani. Muddat: kesim soatidan oldin kelgan ish shu ish kuni,
keyin kelgani keyingi ish kuni oxirigacha (`/company/` da `sla_cutoff_hour`,
`sla_working_days`; dam olish kunlari sanalmaydi).

## Configurator

| Metod | Manzil | Izoh |
|---|---|---|
| GET/POST | `/acts/` | yozish **engineer** (admin) — §11.1: ACT tarkib egasida |
| GET/POST | `/configurations/` | **yozish: engineer (admin)**; qatorlar ixtiyoriy; `quantity` — partiya (#3, tarkib bitta dona uchun o'qiladi) |
| PUT/PATCH/DELETE | `/configurations/{id}/` | faqat `draft` holatida — `ready`/`sold` 400 qaytaradi |
| GET | `/configurations/{id}/stock-check/` | omborda bor/yo'qligi |
| GET | `/configurations/{id}/changes/` | zavod tarkibiga nisbatan farq (modify rejimi uchun) |
| POST | `/configurations/{id}/submit/` | #4: engineer texnik yechimni **sales ko'rigiga** yuboradi (`pending_sales`); zayavka egasiga xabar; YANGI-OQIM B2: **narxsiz qator bo'lsa 400** (nol qatorlar avval ombordan qayta o'qiladi) |
| POST | `/configurations/{id}/approve/` | #4: **sales** (admin) texnik yechimni tasdiqlaydi (`approved`), zayavka `done`; tarix — `approvals[]`; YANGI-OQIM B1: **shu yerda draft SHT avtomatik ochiladi** (egasi — zayavka sales'i, javobdagi `contract` maydonida); mijoz aniqlanmasa **400** (B10) |
| POST | `/configurations/{id}/reject/` | #4: sales izoh bilan qaytaradi (`draft`ga) — engineer xabar oladi, izoh tarixda |
| POST | `/configurations/{id}/finalize/` | #4: shartlari `approved` + yig'ilgan (`assembled_at`) + ACT (tanada `{"act": 2}`); YANGI-OQIM: shartnoma bu yerda OCHILMAYDI (u `approve`da ochilgan) — qatordagi bazaviy model **yig'ilgan variantga ko'chadi** (B6, son/narx tegilmaydi), CFG `ready` (shartnoma `active` bo'lsa `sold`), bron shartnomaga o'tadi |
| POST | `/configurations/{id}/assemble/` | #4/§10.1: yig'ish — faqat `approved` yechim; **B4: shartnoma `active`/`completed` bo'lishi shart** (400: "Boshlang'ich to'lov kutilmoqda — SHT-…"; rad etilgan/bekor qilinganida boshqa matn); build: butlovchilar chiqadi, variant kiradi; modify: tayyor mahsulot fizik o'zgartiriladi (tana: `{"removals": {...}}`); yetmasa 400 (nomlar bilan) — mol TLD orqali kelgach qayta bosiladi; javobda `act_suggestion` (#4D) |
| POST | `/configurations/{id}/request-prices/` | YANGI-OQIM B2: narx so'rovi — **TLD emas**, buyurtmachi tannarxni mahsulot kartasida kiritib beradi; takrorida eslatma yangilanadi (dublikat yo'q); narx kelgach **sales** "mijoz bilan kelishing" xabarini oladi; hammasi narxli bo'lsa 400 |
| POST | `/configurations/{id}/request-procurement/` | **engineer** — yetishmaganlardan TLD ochadi; #4: faqat `approved` konfiguratsiyada; **B4: faqat to'langan zanjirda** (shartnoma `active`) — mol pulga bog'lanadi; hammasi omborda bo'lsa 400; ochiq TLD bor bo'lsa ham 400 |
| POST | `/configurations/{id}/change-quantity/` | 4-to'plam §2 + 6-to'plam §4: partiya sonini o'zgartirish — **sales** (admin; u mijoz bilan kelishadi, engineer emas), tana `{"quantity": 100, "comment": "..."}`; `draft`/`pending_sales`/`approved` da; bron qayta hisoblanadi, zayavka soni ergashadi, `approved` bo'lsa **`pending_sales`ga qaytadi** (narx-muddat qayta kelishiladi); yig'ilgan (`assembled_at`) yoki chernovikdan o'tgan ochiq TLD bo'lsa 400 (TLD raqami bilan); chernovik TLD to'smaydi; **B13: to'lov kelgach 400 — hech narsa o'zgarmaydi**; pul kelmagan draft SHT esa songa ergashadi (qator miqdori va jami qayta yig'iladi) |
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

Yuborilganidan keyin konfiguratsiya javobida flag paydo bo'ladi —
front "Buyurtmachiga yuborilgan" badge'ini shu yerdan oladi:
```json
GET /api/configurations/12/
{
  "...": "...",
  "sent_to_procurement": true,
  "procurement": {
    "id": 4, "number": "TLD-00004",
    "status": "pending_sales",
    "status_display": "Sales — mijoz roziligi kutilmoqda",
    "is_open": true, "created_at": "2026-09-14T10:00:00+05:00"
  }
}
```
`procurement` — oxirgi TLD (yuborilmagan bo'lsa `null`); `is_open=false` —
jarayon tugagan (`cancelled` yoki `delivered`), shunda `sent_to_procurement`
ham `false` bo'ladi va yangi TLD ochish mumkin. Ochiq TLD turganda
`request-procurement` qayta bosilsa **400**: `{"detail": "CFG-00023 uchun
TLD-00004 hisobi allaqachon ochilgan (...)", "replenishment": 4}`.

**`missing` — "Yig'ish" yoki "Buyurtmachiga yuborish" qarori** (3-to'plam §2).
Konfiguratsiya javobida ombordan olinishi kerak-u, yetishmayotgan pozitsiyalar
ro'yxati bor — `required_from_stock` dan quriladi, ya'ni `modify` da bazaviy
model ham shu yerda (`kind` bilan farqlanadi), o'zgarmagan qismlar esa yo'q:
```json
GET /api/configurations/12/
{
  "...": "...",
  "missing": [
    {"product": 12, "name": "Dell OptiPlex 7010 MT", "kind": "machine",
     "needed": 10, "available": 2, "overbooked": 0, "shortage": 8},
    {"product": 27, "name": "Corsair DDR5 32 GB", "kind": "component",
     "needed": 20, "available": 0, "overbooked": 6, "shortage": 26}
  ],
  "missing_count": 2
}
```
Front qoidasi bitta qator: `missing` bo'sh — **"Yig'ish"** tugmasi, bo'sh
emas — **"Buyurtmachiga yuborish · {missing.length}"** ("Yig'ish" umuman
ko'rsatilmaydi: u baribir 400 beradi). `missing_count` — shu ro'yxat uzunligi.
`shortage` teshikni ham yopadi: boshqa hujjatlarga ortiqcha va'da qilingan
bo'lsa `needed` dan ko'p chiqishi mumkin.

**Roadmap (B8)** — javob chizishga tayyor keladi, front hech narsani qayta
hisoblamaydi:
```json
GET /api/configuration-requests/12/roadmap/
{
  "request": {"id": 12, "number": "ZVK-00012", "status": "in_progress"},
  "client_name": "Sof Mebel MChJ",
  "current_key": "prepayment",
  "steps": [
    {"key": "sales_review", "label": "Sales ko'rigi", "state": "done",
     "tone": "success",
     "actor": {"id": 4, "full_name": "Dilshod Rahimov", "role": "sales",
               "role_label": "Sales"},
     "at": "2026-09-20T09:12:00Z", "waiting_days": null, "deadline": null,
     "document": {"type": "configuration", "id": 45, "number": "CFG-00045"},
     "can_open": true, "repeats": 3},
    {"key": "assemble", "label": "Yig'ish", "state": "blocked", "tone": "muted",
     "actor": {"id": null, "full_name": null, "role": "engineer",
               "role_label": "Engineer"},
     "at": null, "waiting_days": null, "deadline": null,
     "document": null, "can_open": false, "repeats": 0}
  ]
}
```
`state`: `done` / `current` / `pending` / `blocked` (13–16 to'lovgacha) /
`skipped` / `cancelled`. **`optional` (6-to'plam §1–2)** — shartli qadamlar
(`price_request`, `admin_approve`, `procurement_sent`, `procurement_chain`):
ular `current`ni "birinchi bajarilmagan" qoidasi orqali OLMAYDI — joriy
bo'lishining yagona yo'li ish haqiqatan boshlangani (narx so'ralgan, TLD
ochilgan). Shart aniq bo'lmasa (`narxsiz qator yo'q`, `missing` bo'sh,
summa chegaradan past) — `skipped`, front chizmaydi; hali noma'lum bo'lsa —
`optional: true` + `pending`, front xiraroq chizadi. `current_key` doim
javobdagi qadamlardan biriga ishora qiladi (§3). **8-to'plam §1**: zanjirda
UMUMAN bo'lmaydigan hujjatning qadamlari ham `skipped` — qo'lda ochilgan
shartnomada ZVK/CFG qadamlari chizilmaydi ("hali boshlanmagan" bo'lib
ko'rinmaydi); qoida: keyingi bosqich hujjati bor-u, oldingisi yo'q bo'lsa,
oldingisi endi hech qachon paydo bo'lmaydi.

**`GET /roadmaps/?state=open&limit=10` (7-to'plam §1)** — bosh sahifa uchun
joriy foydalanuvchi QATNASHAYOTGAN zanjirlar ro'yxati. Qatnashish: zanjirdagi
biror hujjatning egasi (`ZVK.created_by`/`taken_by`, `CFG.created_by`,
`SHT.created_by`) YOKI joriy qadam uning roliga tegishli (bugalter va
buyurtmachi uchun asosiy shart); admin — hamma ochiq zanjir. `state`:
`open` (default) / `closed` / `all`; `limit`: 1–50 (default 10). Javob
`{"count": N, "results": [...]}` — `results[i]` detal `roadmap` javobi
bilan AYNAN bir xil (18 qadam, pul yo'q, `can_open` alohida). Tartib:
muddatdan o'tgan (`danger`) → joriy qadami shu foydalanuvchida → kutish
vaqti bo'yicha kamayish.
`tone`: `success` / `warning` / `danger` (SLA — mavjud `sla_deadline`dan) /
`muted` / `cancelled` (qizil + chizilgan matn — `danger` bilan
adashtirilmasin). `steps` doim 18 ta va tartibda; `repeats` — aylanma
necha marta aylangani; `can_open` — kim qaysi hujjat ichiga kira olishi
(§3.13 matritsasi backendda). **Javobda pulga oid maydon yo'q.**

**`available` manfiy chiqmaydi** (3-to'plam §3) — ham `missing` da, ham
tarkib qatorlarida (`items[].available`): manfiy o'rniga `0` va alohida
`overbooked` maydoni keladi. Front "omborda 0, ustiga 6 dona ortiqcha
va'da qilingan" deb aniq yozadi ("omborda -6" o'rniga).

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

**Finalize'da avtomatik shartnoma.** Yakunlash muvaffaqiyatli bo'lsa, backend
**draft shartnoma** ochib beradi — sales bugalterga yuborishdan oldin shartnoma
(chop etish shakli bilan) tayyor turadi:

- mijoz: tanada `{"client": id}` berilgan bo'lsa o'sha, bo'lmasa zayavkadagi
  (ZVK) mijoz olinadi; mijoz aniqlanmasa shartnoma ochilmaydi (`contract: null`);
- qator: tayyor variant (bo'lmasa bazaviy model), narxi konfiguratsiya narxidan
  (QQS'siz), QQS default 12% qo'shiladi; `total_amount` — QQS bilan;
- javobda: `"contract": {"id": 7, "number": "SHT-00007", "status": "draft"}`;
- shartnoma allaqachon bor bo'lsa (qo'lda ochilgan) — yangisi yaratilmaydi.

Sales shartnomani ochib tekshiradi, kerak bo'lsa tahrirlaydi va `submit` qiladi.

---

## Kirim (Purchases)

| Metod | Manzil | Izoh |
|---|---|---|
| GET/POST | `/purchases/` | yozish: admin, bugalter |
| POST | `/purchases/{id}/receive/` | omborga kirim + kassaga chiqim; xarid narxi katalogga yoziladi (`cost_price`) |
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
| GET/POST | `/contracts/` | admin, sales; filtr: `status`, `client`, `currency`, `configuration`; 8-to'plam §3: `configuration` bilan ikkinchi shartnoma ochilmaydi (400 — yangi oqimda u tasdiqda avtomatik ochiladi); qo'lda tuzish ombordan to'g'ridan-to'g'ri sotuv uchun |
| POST | `/contracts/{id}/submit/` | sales; bugalterga bildirishnoma tushadi |
| POST | `/contracts/{id}/send-didox/` | B3: **bugalter** — «Didoxga yubordim»; `didox_number` majburiy, `pending_bugalter` → `pending_didox`, `didox_sent_at`/`signed_at` to'ladi |
| POST | `/contracts/{id}/confirm-didox/` | B3: **bugalter** — «Didox tasdiqladi (mijoz imzoladi)»; `didox_accepted_at` yoziladi, keyin §11.3 chegara mantig'i: `pending_admin` yoki `approved`; Didox rad javobi kiritilmaydi — `pending_didox`dan orqaga yo'l yo'q |
| POST | `/contracts/{id}/approve/` | admin bosqichi (`pending_admin` → `approved`); B11 mosligi: `pending_bugalter`dan eski bitta qadamli yo'l ham qabul qilinadi (tanada `didox_number`); har bosqichda keyingi bosqich egasiga bildirishnoma |
| POST | `/contracts/{id}/reject/` | bugalter / admin |
| POST | `/contracts/{id}/ship/` | #2: **yetkazish** — mol shu yerda chiqadi (buyurtmachi/bugalter, admin); `delivered_at` yoziladi, bron chiqimga aylanadi, balans yopiq bo'lsa `completed` |
| POST | `/contracts/{id}/request-procurement/` | #2: **sales (egasi)** — band qilinmagan qismidan TLD ochadi (`contract` FK, `owner_sales`); bitta ochiq TLD qoidasi |
| POST | `/contracts/{id}/confirm-payment/` | bugalter; YANGI-OQIM: bu **ish boshlanish signali** — CFG broni qattiqlashadi, engineer xabar oladi, 13–16 qadamlar ochiladi |
| GET | `/contracts/{id}/timeline/` | hamma |
| GET | `/contracts/{id}/print/` | **faqat sales, admin** — chop etish shakli (qator narxlari bor) |
| GET | `/contracts/deadlines/` | hamma |
| GET/POST | `/contract-items/` | admin, sales |
| GET/POST | `/contract-payments/` | admin, bugalter; POST `confirm-payment` bilan bir xil yo'ldan o'tadi: `paid_at` ixtiyoriy (default: hozir), kassaga kirim, balans yopilsa `completed`; §3: summa qoldiqdan oshsa yoki ≤0 bo'lsa `400` |
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
    {"product": 1, "quantity": 1, "unit_price": "500000000", "vat_percent": "12"}
  ]
}
```
`total_amount` yuborilmasa qatorlardan **QQS bilan** hisoblanadi (mijoz to'laydigan real summa). `prepayment_percent` bo'sh bo'lsa avtomatik 30% yoki 15% — QQS bilan jamidan.

**QQS:** har bir qatorda `vat_percent` bor — default **12%**, imtiyozli mahsulotga `0`
yuborsa bo'ladi. `unit_price` — **QQS'siz sof narx**. Javobda hisoblab beriladi:

```json
{
  "items": [
    {"product": 1, "quantity": 1, "unit_price": "5000000.00",
     "subtotal": "5000000.00", "vat_percent": "12.00",
     "vat_amount": "600000.00", "total_with_vat": "5600000.00"}
  ],
  "items_total": "5000000.00",
  "vat_total": "600000.00",
  "items_total_with_vat": "5600000.00",
  "total_amount": "5600000.00"
}
```

`items_total` — Yetkazish jami (QQS'siz), `vat_total` — QQS jami,
`items_total_with_vat` — Jami (chop etishdagi pastki qator).

**Chop etish shakli** — rasmiy shartnoma modalini chizish uchun hamma narsa
bitta javobda (bajaruvchi `/company/` dan, buyurtmachi — mijoz):

```json
GET /api/contracts/7/print/
{
  "number": "SHT-00007",
  "signed_at": "2026-08-18", "start_date": null,
  "term_days": 90, "deadline": null, "currency": "UZS",
  "company": {"name": "Swiftcore MCHJ", "inn": "305123456",
    "phone": "+998911198877", "email": "swiftcore@gmail.com",
    "address": "Toshkent shahri, Yunusobod tumani",
    "bank_name": "...", "mfo": "...", "account_number": "...",
    "director_name": "..."},
  "client": {"name": "Navoiy Qurilish Servis", "type": "legal",
    "inn": "301111111", "phone": "+998900000002", "email": "...",
    "address": "...", "bank_name": "...", "mfo": "...",
    "account_number": "...", "director_name": "...", "jshshir": "..."},
  "items": [{"name": "adas", "sku": "ADS-1", "unit": "dona",
    "quantity": 1, "unit_price": "5000000.00", "vat_percent": "12.00",
    "vat_amount": "600000.00", "total_with_vat": "5600000.00"}],
  "totals": {"items_total": "5000000.00", "vat_total": "600000.00",
    "total": "5600000.00", "total_amount": "5600000.00",
    "prepayment_percent": "30.00", "prepayment_amount": "1680000.00"},
  "terms": "To'lov 30% oldindan...",
  "note": "CFG-00012 konfiguratsiyasi asosida avtomatik ochildi"
}
```

`client.name` — tayyor `display_name` (jismoniy: F.I.SH, yuridik: kompaniya
nomi). Bugalter uchun `print/` yopiq (403) — qator narxlari bor.

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
Natija: `status = active`, `start_date = bugun`, kassaga `sale` kirimi
tushadi. Mol bu yerda **chiqmaydi** — chiqim alohida `ship` hodisasi (§8.30);
balans yopilib mol YETKAZILGAN bo'lsa shartnoma `completed` bo'ladi.

**Summa chegarasi (4-to'plam §3):** nol/manfiy summa yoki qoldiqdan katta
summa — `400`, kassaga hech nima yozilmaydi:

```json
{"amount": "To'lov qoldiqdan ko'p: qoldiq 9296000.00 UZS. Ortiqcha to'lov
shartnomaga yozilmaydi — qaytarish yoki avans alohida hujjat bilan
rasmiylashtiriladi."}
```

`amount` yuborilmasa oldindan to'lov summasi olinadi; ANIQ `0` yuborilsa
esa default olinmaydi — `400`. Balansi manfiy eski shartnomada chegara `0`
deb olinadi (`400`, `500` emas).

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

> Eslatma: `items[].unit_price`, `subtotal`, `vat_percent`, `vat_amount`,
> `total_with_vat` faqat sales va admin javobida bo'ladi (bugalterga umumiy
> `total_amount`, `items_total`, `vat_total` ko'rinadi).

---

## Omborni to'ldirish — Buyurtmachi (TZ 7)

| Metod | Manzil | Kim |
|---|---|---|
| GET | `/replenishments/low-stock/?warehouse=1` | hamma |
| POST | `/replenishments/from-low-stock/` | buyurtmachi |
| GET/POST | `/replenishments/` | yozish: admin, buyurtmachi |
| GET/PUT/PATCH/DELETE | `/replenishments/{id}/` | admin, buyurtmachi |
| POST | `/replenishments/{id}/submit/` | buyurtmachi; konfiguratsiya YOKI shartnomadan ochilgan hisob sales bosqichiga boradi; keyingi bosqich egasiga bildirishnoma tushadi |
| POST | `/replenishments/{id}/approve/` | mijoz buyurtmasidan ochilganda: avval **sales** (mijoz roziligi), keyin bugalter, keyin admin; oddiy to'ldirishda bugalter → admin; summa `replenishment_approval_threshold` dan kichik (UZS) bo'lsa admin bosqichi o'tkazib yuboriladi (tarixda avtomatik yozuv); har tasdiqda keyingi bosqich egasiga bildirishnoma tushadi |
| POST | `/replenishments/{id}/reject/` | bugalter / admin |
| POST | `/replenishments/{id}/pay/` | bugalter; `debt_amount` satr/son bo'lishi mumkin, noto'g'ri format 400 |
| POST | `/replenishments/{id}/events/` | buyurtmachi / bugalter |
| POST | `/replenishments/{id}/receive/` | buyurtmachi / bugalter; xarid narxi katalogga yoziladi (`cost_price`) |
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
  "unit_price": "350000",
  "vat_percent": "12"
}
```

- `product_name` yuborilsa va bunday mahsulot bazada bo'lmasa — u **katalogga qo'shiladi**
  (`product_sku` berilmasa, `MAH-00001` ko'rinishida raqam beriladi)
- Bazada bor mahsulot uchun oddiy `"product": 5` yuboriladi
- Nomi mos keladigan mahsulot bo'lsa, dublikat yaratilmaydi
- `product` ham, `product_name` ham bo'lmasa — `400`
- `vat_percent` — QQS foizi, **default 0**: ta'minotchi hisobida QQS bo'lsa
  kiritiladi; javobda `vat_amount` va `total_with_vat` hisoblab beriladi
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
  "vat_total": "0.00",
  "items_total_with_vat": "1200000.00",
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

**Tasdiqlash zanjiri:** konfiguratsiyadan (mijoz buyurtmasidan) ochilgan hisob
`submit`dan keyin **`pending_sales`** bo'ladi — sales'larga notification tushadi,
sales mijoz bilan kelishib `approve` qiladi (rozi bo'lmasa `reject` — hisob
buyurtmachiga qaytadi); shundan keyingina `pending_bugalter` → `pending_admin`
→ `approved`. Oddiy to'ldirish `submit`da to'g'ri `pending_bugalter`ga o'tadi.
Tarixda `approvals[].step`: `sales` / `bugalter` / `admin`.

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

## Bajaruvchi rekvizitlari (Company)

Shartnoma chop etishda chiqadigan **o'z firmamiz** (bajaruvchi) rekvizitlari.
Tizimda yagona yozuv: birinchi `GET` da bo'sh holda o'zi ochiladi.

| Metod | Manzil | Kim |
|---|---|---|
| GET | `/company/` | hamma (autentifikatsiyalangan) |
| PUT/PATCH | `/company/` | **faqat admin** |

```json
PUT /api/company/
{
  "name": "Swiftcore MCHJ",
  "inn": "305123456",
  "phone": "+998911198877",
  "email": "swiftcore@gmail.com",
  "address": "Toshkent shahri, Yunusobod tumani",
  "bank_name": "Kapitalbank",
  "mfo": "01088",
  "account_number": "20208000900000000001",
  "director_name": "Karimov A.",
  "contract_terms": "To'lov 30% oldindan..."
}
```

Javobda shu maydonlar + `updated_at`. Sales/bugalter yozsa — `403`.
`contract_terms` — shartnoma pastida chiqadigan standart shartlar matni.

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
| GET | `/notifications/` | faqat o'ziniki; filtr: `is_read`, `level`, `entity`, `object_id` (§4: "shu hujjat bo'yicha xabarlar") |
| POST | `/notifications/{id}/mark-read/` | egasi |
| POST | `/notifications/mark-all-read/` | 4-to'plam §4: o'zining BARCHA o'qilmaganlarini bittada yopadi — javob `{"updated": N}`; bitta UPDATE, birovnikiga tegmaydi |

Audit filtri: `?user=3&action=approve&entity=Contract`.
