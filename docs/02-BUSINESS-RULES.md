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

### Import hujjatlari (TZ 2.2)

Har bir kirimga bir nechta hujjat biriktiriladi — `PurchaseDocument`:
`contract` (shartnoma), `invoice` (invoys), `customs` (bojxona deklaratsiyasi), `other`.
Hujjatlar bilan **bugalter** ishlaydi (TZ 8.2): yuklash va o'zgartirish faqat unda
(va adminda), buyurtmachi ko'radi, sales bu bo'limga kirmaydi.
`POST /api/purchase-documents/` (multipart), kirim javobida `documents[]`.

> Bojxona boji va soliq (`customs_duty`, `tax_amount`) hozircha **qo'lda** kiritiladi —
> TZ "avtomatik hisoblanishi kerak" deydi, lekin stavkalar (qiymat chegaralari va foizlar)
> TZ da berilmagan. Stavkalar aniqlashgach avtomatik hisob qo'shiladi.

---

## 2. Chiqim

| Tur | Qayerda |
|---|---|
| Mijozga sotuv (so'mda) | `apps/sales` — birinchi to'lov tasdiqlanganda mahsulot **ombordan chiqim qilinadi** (TZ 9); yetmasa to'lov bloklanadi |
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

| Holat | Rang | 90 kunlik shartnomada |
|---|---|---|
| Muddat boshi | `green` (yashil) | 90–31 kun |
| Oxirgi uchdan bir | `yellow` (sariq) | 30–11 kun |
| **Oxirgi 10 kun va muddatdan o'tgan** | `red` (qizil) | 10–0 kun |
| Sanoq boshlanmagan | `grey` | — |

Qoida `apps/core/utils.py` da: `RED_ZONE_DAYS = 10`, `YELLOW_ZONE_RATIO = 1/3`.
Chegaralar har bir shartnoma muddatiga proporsional hisoblanadi (TZ 5.3).

`GET /api/contracts/{id}/timeline/` har bir kun uchun `{date, days_left, color}` qaytaradi — to'g'ridan-to'g'ri line chartga beriladi.

`GET /api/contracts/deadlines/` — faol shartnomalar, eng kam kun qolgani birinchi.

### Eslatmalar

`manage.py check_deadlines` — sariq va qizil zonadagi shartnoma, qarz va importlar,
hamda "Keyingi aloqa" sanasi kelgan yoki o'tib ketgan kelishuvlar (`Lead`) uchun
`Notification` yaratadi. Kelishuv eslatmasi uni yaratgan sales'ning o'ziga boradi:
bugun/ertaga — sariq, o'tib ketgan — qizil; sana kiritilmagan bo'lsa eslatma yo'q.
Takroran ishga tushirilsa dublikat yaratmaydi (idempotent).

### QQS (NDS)

Sotuv qatorida narx **QQS'siz** kiritiladi, QQS foizi qatorda alohida turadi:
default **12%** (`root/settings/business.py` → `DEFAULT_VAT_PERCENT`), imtiyozli
mahsulotga 0% qo'yish mumkin. Hujjat bo'yicha: Yetkazish jami (QQS'siz) + QQS
jami = Jami — shartnoma `total_amount` i va undan olinadigan oldindan to'lov
(30%/15%) ham **QQS bilan** hisoblanadi.

To'ldirish (TLD) qatorlarida QQS default **0** — ta'minotchi hisobida QQS bo'lsa
buyurtmachi foizni o'zi kiritadi; to'lov va qarz (shortfall) QQS bilan jamidan.

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
   - `unit_price` — kiritilmagan bo'lsa **ombordagi narx avtomatik olinadi**
     (sotuv narxi, bo'lmasa tannarx)
   - `needs_price` — omborda ham narx yo'q; bunday qator bo'lsa yakunlash bloklanadi
4. `GET /api/configurations/{id}/stock-check/` — shu ro'yxatni qaytaradi.
5. **ACT majburiy:** `POST /{id}/finalize/` faqat `act` biriktirilgan va qatorlari bor bo'lsa ishlaydi.
   ACT ni **sales** kiritadi (admin ham mumkin; `/api/acts/` yozish `IsAdminOrSales`).
   Engineer konfiguratsiyani ACT'siz tayyorlab `complete` qiladi — ACT va
   yakunlash sales bosqichida, so'ng shartnoma bugalterga yuboriladi.
6. `GET /{id}/export-excel/` — chernovik Excel (butlovchi, miqdor, narx, omborda, yetishmaydi, manba, jami).
7. Tayyor bo'lsa `POST /{id}/attach/` bilan kirim buyurtmasiga biriktiriladi → status `attached`.

### Tayyor variantni tanish (TZ 6.2)

Har bir konfiguratsiya tarkibi **imzo** bilan saqlanadi (`Product.signature`) — bazaviy model +
butlovchilar va ularning miqdori. Shu sababli:

- Aynan shunday kombinatsiya avval yig'ilgan bo'lsa, tizim uni taniydi va
  **ombordagi tayyor pozitsiya narxini** qo'llaydi (`ready_variant`, `total_price`)
- Yangi kombinatsiya yakunlanganda omborga **alohida mahsulot** bo'lib qo'shiladi
  (`sku` = `HP-880-V01`, `base_model` = bazaviy model), keyingi safar qayta ishlatiladi
- Komponentlar tartibi ahamiyatsiz: `SSD + GPU` va `GPU + SSD` bir xil imzo beradi
- **Bazaviy modelning o'zi ham tayyor pozitsiya**: tarkib zavod tarkibiga teng bo'lsa,
  tizim aynan bazaviy modelni taniydi — uning ombordagi narxi va qoldig'i qo'llanadi,
  yangi variant yaratilmaydi
- Model tanlanganda **zavod tarkibi avtomatik yuklanadi** (`items` yuborilmasa) —
  ichidagi barcha narsa tayyor keladi, foydalanuvchi faqat keraklisini o'zgartiradi (TZ 6.1)

### Ikki rejim: yig'ish va tayyor mahsulotni o'zgartirish

| Rejim | Nima bo'ladi |
|---|---|
| `build` | Butlovchilardan yangi mahsulot rejalashtiriladi; yetishmagani kirim orqali to'ldiriladi. Yakunlashda ombor harakati bo'lmaydi |
| `modify` | **Ombordagi butun tayyor mahsulot olinadi** va ichi o'zgartiriladi: qo'shilgan qism ombordan chiqadi, **yechib olingani omborga qaytadi** (narxi bilan, narxni o'zgartirish mumkin), o'zgartirilgan mahsulot tayyor pozitsiya sifatida omborga kiradi. Yechib olinganlar haqida **bugalterga ACT bilan xabar** boradi |

Configurator **barcha rollarga** ochiq (TZ 6.5).

---

## 6. Client

| Jismoniy shaxs | Yuridik shaxs |
|---|---|
| F.I.SH — majburiy | Kompaniya nomi — majburiy, unique |
| Passport — majburiy, unique | INN — majburiy, unique |
| JSHSHIR — majburiy, unique | JSHSHIR — majburiy, unique |
| Telefon — majburiy, unique | **MFO — majburiy** |
| Email — optional | **Bank nomi — majburiy** |
| Izoh — optional | **Hisob raqam — majburiy, unique** |
| | Rahbar F.I.SH — majburiy |
| | Telefon — majburiy, unique |
| | Email, manzil, izoh — optional |

> TZ 2.1 da bank rekvizitlari qo'shildi, manzil esa majburiydan ixtiyoriyga o'tdi.

Client qo'shish **bugalterda yo'q** — sales, buyurtmachi va adminda bor (TZ 11).

---

## 7. Buyurtmachi — omborni to'ldirish (TZ 7)

> **Mahsulot qo'shish shu yerda bo'ladi.** TZ da alohida katalog boshqaruvi yo'q:
> buyurtmachi to'ldirish hisobiga hali bazada yo'q tovarni yozsa (`product_name`),
> o'sha tovar katalogga qo'shiladi. Ya'ni buyurtma qilishning o'zi mahsulot qo'shishdir.

**Buyurtmachi** tashqi mijoz bilan emas, ombor va ta'minot bilan ishlaydi.

### Jarayon

| # | Bosqich | Kim | Endpoint |
|---|---|---|---|
| 1 | Yetishmayotganlar ro'yxati | hamma ko'radi | `GET /replenishments/low-stock/` |
| 2 | Hisob shakllantirish | buyurtmachi | `POST /replenishments/from-low-stock/` |
| 3 | Ta'minotchi narxlari, logistika va boshqa xarajatlar | buyurtmachi | `PATCH /replenishments/{id}/` |
| 4 | Tekshiruvga yuborish | buyurtmachi | `POST /{id}/submit/` |
| 4a | **Mijoz roziligi** — konfiguratsiyadan ochilgan hisobda | **sales** | `POST /{id}/approve/` yoki `/{id}/reject/` |
| 5 | Tekshirish | bugalter | `POST /{id}/approve/` |
| 6 | Tasdiqlash, miqdorni o'zgartirish, pozitsiya o'chirish | **admin** | `POST /{id}/approve/`, `PATCH/DELETE /replenishment-items/{id}/` |
| 7 | To'lov | bugalter | `POST /{id}/pay/` |
| 8 | Yetkazib berish bosqichlari (bojxona va h.k.) | buyurtmachi / bugalter | `POST /{id}/events/` |
| 9 | Omborga kirim | buyurtmachi / bugalter | `POST /{id}/receive/` |

**Admin chegarasi TLD da ham (TOPSHIRIQ #2):**
`CompanyProfile.replenishment_approval_threshold` — shu summadan kichik UZS
hisob bugalter tasdig'i bilan to'g'ridan-to'g'ri `approved` bo'ladi
(shartnoma chegarasidan alohida maydon; qoidalari bir xil: QQS+xarajatlar
bilan, faqat UZS, 0 — chegara yo'q, tarixda avtomatik yozuv).

**Sales-gate qoidasi:** mijoz buyurtmasidan (konfiguratsiyadan) ochilgan hisob
`submit`da avval **sales**ga boradi (`pending_sales`) — sales mijoz bilan
narxlarni kelishib tasdiqlagachgina bugalter/adminga tushadi; mijoz rozi
bo'lmasa sales qaytaradi va hisob bugalter/admin stolini band qilmaydi.
Hammasi omborda bo'lsa TLD umuman ochilmaydi (`request-procurement` 400) —
engineer `complete` qiladi, sales shartnoma bilan davom etadi.

**Texnik tasdiq (#4):** engineer yig'ib bo'lgach `submit` — konfiguratsiya
sales ko'rigiga o'tadi; sales mijozga ko'rsatib `approve` (zayavka `done`)
yoki izoh bilan `reject` (chernovikka qaytadi, engineer xabar oladi).
Ta'minot va yig'ish faqat `approved`dan keyin; `finalize` endi bitta ish —
`approved` + yig'ilgan + ACT bo'lsa `ready` qiladi va shartnoma ochadi.
Ikki xil tasdiq bor: **texnik** (shu tarkib to'g'rimi — konfiguratsiyada)
va **narx** (mijoz summaga rozimi — TLD `pending_sales`).

**Yig'ish qadami (§10.1):** `build` rejimida `finalize` endi jismoniy
yig'ishni ham qiladi — butlovchilar ombordan chiqadi, variant 1 dona kirim
bo'ladi (shu tufayli shartnoma to'lovi o'tadi). Butlovchi yetmasa finalize
bloklanmaydi: yig'ish keyinga qoladi (`assembly_missing` ro'yxati), mol
kelgach `POST /configurations/{id}/assemble/` yoki to'lov paytida avtomatik
yig'iladi.

**Bron (§11.4):** shartnoma tuzilishi bilan mahsulot **band** (qattiq bron),
konfiguratsiya chernovigi esa **rejada** (yumshoq — to'smaydi, ogohlantiradi).
Chiqim vaqti o'zgarmagan (to'lovda), bron shartnoma–to'lov oralig'idagi oynani
yopadi: yetishmovchilik endi to'lovda emas, shartnoma tuzilayotganda ko'rinadi.
Har amal o'z bronini o'ziga ochiq hisoblaydi. Muddati o'tgan bron
`check_deadlines`da bo'shaydi. Yig'ilmagan variantda bron butlovchilarga tushadi.

**Tannarx yangilanishi:** `receive` (TLD ham, KIR ham) har bir qator
uchun mahsulot `cost_price`ini xarid narxi (QQS'siz `unit_price`) bilan
yangilaydi — katalogda narxsiz mahsulot qolmaydi. TLD konfiguratsiyadan
ochilgan bo'lsa, o'sha konfiguratsiyaning narxsiz qatorlari ham kirimdan
keyin avtomatik narx oladi (`needs_price` o'chadi, finalize ochiladi).

**§11 kelishilgan o'zgarishlar (endi kodda):** ACT va `finalize` —
engineerda (§11.1, "Yakunlash va salesga topshirish"); bugalter tasdig'i ikkiga
bo'lindi — "Didox qabuli" (`didox_number` saqlanadi) va "boshlang'ich to'lov"
(tarixga `payment` qadami yoziladi) (§11.2); `admin_approval_threshold` dan
kichik UZS shartnoma admin tasdig'isiz o'tadi, tarixda avtomatik yozuv qoladi,
boshqa valyuta doim adminga (§11.3). Shartnoma va qatorlari tasdiqqa
yuborilgach qulflanadi (faqat admin), qator o'zgarganda `total_amount`
avtomatik qayta hisoblanadi (§10.3); rad etilgani tuzatilib qayta yuboriladi.

**Hujjat egaligi (EGALIK §3):** sales va engineer ko'p, shuning uchun
ularda egalik filtri bor: sales faqat o'z shartnomasi/kelishuvi/zayavkasini
(va o'z zayavkasidan tug'ilgan konfiguratsiyani), engineer o'z
konfiguratsiyasi + hali olinmagan `new` zayavkalarni ko'radi; TLD da sales o'z hisobini
butun yo'l davomida ko'radi (amal esa faqat `pending_sales`da), egasizini —
faqat `pending_sales`da. Bugalter/admin zanjirda —
hammasini ko'radi; buyurtmachi bitta bo'lim — TLD ni to'liq ko'radi.
Yozish — faqat egasi va admin. Admin to'liq zaxira: ta'tildagi sales o'rniga
ko'radi, tahrirlaydi va yubora oladi. Avtomatik shartnoma egasi — zayavkani
yozgan sales.

**Hovuz va egalik (EGALIK §4):** bildirishnoma yo hovuzga (roldagi har
bir odamga alohida yozuv — keyingi qadamni istalgani bajara oladi), yo
egasiga (faqat u bajara oladi) boradi; `user=None` umumiy xabar taqiqlangan.
Sales hovuz emas: TLD bo'yicha xabarlar zayavka egasiga (`owner_sales`)
boradi. Muddat eslatmalari: shartnoma — egasi+bugalter+admin, qarz —
bugalter+admin, kirim — bugalter+buyurtmachi, kelishuv — egasi.

**Bildirishnomalar:** har bir tasdiq navbatni keyingi bosqich egasiga
o'tkazganda unga `/notifications/` orqali xabar tushadi: submit'da sales
(mijoz buyurtmasi) yoki bugalterga, sales tasdig'ida bugalterga, bugalter
tasdig'ida adminga, admin tasdig'ida bugalter (to'lov) va buyurtmachiga.
Shartnoma zanjirida ham xuddi shunday.

**Bitta konfiguratsiya — bitta ochiq TLD:** ochiq (bekor/kirim qilinmagan)
hisob turganda `request-procurement` qayta chaqirilsa 400 qaytadi — ikkita
parallel hisob ochilib ketmaydi. Konfiguratsiya javobidagi
`sent_to_procurement` va `procurement` maydonlari jarayon holatini ko'rsatib
turadi (`rejected` — hali ochiq: buyurtmachi to'g'irlab qayta yuboradi).

### Pul yetmagan holat

Admin oynasida doimo ko'rinadi:

| Maydon | Ma'nosi |
|---|---|
| `items_total` | Pozitsiyalar yig'indisi |
| `logistics_cost`, `other_cost` | Buyurtmachi kiritgan xarajatlar |
| `total_amount` | Umumiy summa |
| `cash_available` | Kassadagi mavjud pul |
| `shortfall` | Yetmayotgan qism |

**Qarz va kassa (TOPSHIRIQ-2 #1):** ta'minotchi qarzi (`source=supplier`)
kassaga KIRIM yozmaydi — u majburiyat, pul harakat qilmaydi; kassa u bilan
faqat `repay` (chiqim) da uchrashadi. Shaxsiy qarz (`source=personal`) esa
haqiqiy pul kelishi — kirim yoziladi. Shu tufayli jami chiqim mol qanchaga
tushgan bo'lsa shuncha bo'ladi.

TZ 7.1 misoli: summa **1 400 000**, kassada **500 000** → **900 000** avtomatik hisoblanadi va
`POST /pay/` da shu qism **qarzga** o'tqaziladi.

### Qarz (TZ 7.2)

- `Loan` yaratiladi: `source = supplier`, `lender_name` = ta'minotchi
- Muddat: **mahsulot omborga kirim qilingan kundan 60 kun** (`receive` da qayta hisoblanadi)
- Rang kodi va eslatmalar shartnoma bilan bir xil (yashil → sariq → oxirgi 10 kun qizil)
- Shaxsiy qarz (`source = personal`) va ta'minotchi qarzi bitta `Loan` modelida yuritiladi

### Yetkazib berish kuzatuvi (TZ 7.3)

Bosqichlar: `ordered` → `shipped` → `customs` → `cleared` → `arrived`.
Har bir bosqich `ReplenishmentEvent` sifatida vaqti va izohi bilan saqlanadi,
`GET /{id}/timeline/` da qarz muddati bilan birga qaytariladi.

## 8. Audit

Har bir yaratish / o'zgartirish / o'chirish / tasdiqlash `ActivityLog` ga tushadi
(`BaseModelViewSet` avtomatik yozadi). Ro'yxat faqat adminga: `GET /api/activity-logs/`.
