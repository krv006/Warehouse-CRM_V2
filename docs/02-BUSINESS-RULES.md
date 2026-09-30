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
| `pending_bugalter` | Bugalter bandlarni ko'radi | `send-didox` → `pending_didox` (B3; eski `approve` ham qabul qilinadi) |
| `pending_didox` | Mijoz Didoxda imzolashi kutilmoqda | `confirm-didox` → `pending_admin` / `approved` (chegara); orqaga yo'l yo'q |
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

### To'lov summasi chegarasi (4-to'plam §3)

To'lov **qoldiqdan oshmaydi** va **noldan katta** bo'lishi shart — ikkala
yo'lda ham (`confirm-payment` va `POST /contract-payments/`, ular bitta
servisdan o'tadi). Aks holda kassaga haqiqatda kelmagan pul kirim bo'lib,
balans manfiyga tushar va hisobot yolg'on bo'lardi (jonli SHT-00036:
9,3 mln lik shartnomaga 653,5 mln yozilgan edi). Ortiqcha to'lov
shartnomaning ishi emas — qaytarish yoki avans alohida hujjat bilan.
Balansi allaqachon manfiy eski shartnomalarda chegara 0 deb olinadi —
ular 500 emas, tushunarli 400 oladi.

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

**Eslatma — vazifa, arxiv emas (4-to'plam §4).** Hujjat bosqichdan o'tishi
bilan o'sha bosqich eslatmasi eskiradi, shuning uchun har bir o'tish amali
(`contract.approve/reject/confirm-payment/ship`,
`configuration.approve/reject/assemble/finalize`,
`replenishment.approve/pay/receive`) **ishni bajargan odamning** shu hujjat
bo'yicha o'qilmagan eslatmalarini avtomatik yopadi
(`resolve_notifications(entity, object_id, user=...)`, `apps/core/services.py`).
Boshqa odamlarniki turadi. Shunda qo'ng'iroqchadagi son "sizda N ta ish bor"
degan haqiqiy ma'noga ega bo'ladi. Qo'lda tozalash:
`POST /notifications/mark-all-read/`.

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

### Marja nazorati — tannarxdan past sotuvga ogohlantirish (27-to'plam)

Sales tannarxdan past yoki teng narxda sotmasligi kerak; admin eng kam
ustamani belgilaydi. Bu **qat'iy taqiq emas** — shartnoma baribir
tuziladi, faqat ogohlantirish rangi turadi. `CompanyProfile.
min_margin_percent` (default 0) — `markup_percent` bilan **chalkashtirilmasin**:
u narxsiz mahsulotga avtomatik ustama qo'yadi (narxni **yasaydi**), bu esa
qo'yilgan narxni **tekshiradi**.

```
subtotal  = quantity × unit_price                    # QQS'siz
cost      = ContractItem.cost (qator turiga qarab, pastga qarang)
min_price = cost × (1 + min_margin_percent / 100)

cost yo'q (0)            → margin_state = 'unknown'   (rang yo'q)
subtotal <= cost          → 'below_cost'   🔴 (teng bo'lsa ham qizil)
cost < subtotal < min_price → 'below_min'  🟡
subtotal >= min_price     → 'ok'
```

`ContractItem.cost` qator turiga qarab to'rt xil (`Configuration.
cost_total`ga tayanadi):

| Qator turi | Tannarx |
|---|---|
| Oddiy (konfiguratsiyasiz) | `product.cost_price × quantity` |
| `build` | `Σ(component.cost_price × item.quantity) × quantity` |
| `order` | `base_product.cost_price × quantity` (25-§6) |
| `modify` | `(base_product.cost_price + qo'shilgan − yechilgan) × quantity` |

`Configuration.cost_known` — tannarx TO'LIQ hisoblanganini bildiradi;
`build`da bitta butlovchining tannarxi yo'q bo'lsa ham butun qator
`unknown` (yarim hisoblangan tannarx bilan solishtirish yolg'on natija
berardi). Shartnoma valyutasi UZS bo'lmasa tekshiruv o'tkazib yuboriladi
(`unknown`) — tannarx so'mda, kursni solishtirish yolg'on ogohlantirish
berardi.

`Contract.margin_state` — ENG YOMON qator bo'yicha jamlanma (`unknown`
eng yomon SANALMAYDI: bitta qator `unknown`, qolgani `ok` bo'lsa
jamlanma `ok`).

**Kim nimani ko'radi** (`ContractItemSerializer`/`ContractSerializer`):

| Rol | `margin_state` | `min_price` | `cost` |
|---|---|---|---|
| Admin | ✅ | ✅ | ✅ |
| Sales | ✅ | ✅ | ❌ (tannarxni hech qachon ko'rmaydi) |
| Bugalter | ✅ | ❌ | ❌ |
| Boshqalar (shu jumladan buyurtmachi) | ❌ | ❌ | ❌ |

> 29-§2: qator darajasidagi qirqish (`ContractItemSerializer`) boshidanoq
> to'g'ri ishlagan; shartnoma darajasidagi jamlanma (`ContractSerializer.
> margin_state`) esa avval umuman qirqilmagan edi — buyurtmachi ba'zi
> shartnomalarni ko'radi (o'zi yetkazgan/o'zi TLD ochgan,
> `apps/sales/views.py` `get_queryset`), va aynan u bizga tannarxni
> beradigan tomon bo'lgani uchun bu haqiqiy teshik edi. Ikkalasi ham endi
> bir xil qoidaga bo'ysunadi.

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

### Tayyor variantni tanish (TZ 6.2, 21-§1 bilan yangilangan)

Har bir konfiguratsiya tarkibi **imzo** bilan hisoblanadi (`configuration_signature`) —
bazaviy model + butlovchilar va ularning miqdori (tartib ahamiyatsiz:
`SSD + GPU` va `GPU + SSD` bir xil imzo beradi). 21-§1.3: bitta buyurtma
uchun yig'ilgan mashina uchun **alohida katalog yozuvi (variant) endi
umuman yaratilmaydi** — bu yig'ilgan narsa boshqa mijozga sotib bo'lmaydi,
katalogda turishi xato edi (variant `Product.kind=machine`,
`base_model`=bazaviy model bo'lib yaratilardi va low-stock/TLD/katalog
ro'yxatlarini ko'mib tashlardi — jonli o'lchov: 51 ta mahsulotning 21 tasi,
31 ta TLD yozuvining 13 tasi variant edi).

- **Bazaviy modelning o'zi tayyor pozitsiya**: tarkib zavod ProductSpec'iga
  aynan teng bo'lsa (`Configuration.matching_variant`), yig'ish shart emas —
  mol bevosita bazaviy modelning ombordagi narxi va qoldig'idan ketadi
  (`total_price` esa har doim `items_total` — qatorlar yig'indisi, alohida
  "variant narxi" tushunchasi yo'q)
- Tarkib o'zgartirilgan bo'lsa (`matching_variant` topilmaydi) — mahsulot
  har doim butlovchilardan yig'iladi, natija hech qanday yangi katalog
  yozuviga aylanmaydi
- Model tanlanganda **zavod tarkibi avtomatik yuklanadi** (`items` yuborilmasa) —
  ichidagi barcha narsa tayyor keladi, foydalanuvchi faqat keraklisini o'zgartiradi (TZ 6.1)
- Eski (21-to'plamgacha) yaratilgan variantlar bazada qoladi, lekin
  `is_active=False` qilib o'chirilgan va katalog/TLD ro'yxatlarida sukut
  bo'yicha yashiringan (`?include_variants=true` bilan audit uchun ko'rinadi)

### Uch rejim: yig'ish, tayyor mahsulotni o'zgartirish, butun model buyurtma qilish

| Rejim | Nima bo'ladi |
|---|---|
| `build` | Butlovchilardan yangi mahsulot rejalashtiriladi; yetishmagani kirim orqali to'ldiriladi. Yakunlashda ombor harakati bo'lmaydi |
| `modify` | **Ombordagi butun tayyor mahsulot olinadi** va ichi o'zgartiriladi: qo'shilgan qism ombordan chiqadi, **yechib olingani omborga qaytadi** (narxi bilan, narxni o'zgartirish mumkin), o'zgartirilgan mahsulot tayyor pozitsiya sifatida omborga kiradi. Yechib olinganlar haqida **bugalterga ACT bilan xabar** boradi. **Tayyor model — yaxlit birlik** (3-to'plam §1): ombor bilan aloqa faqat modelning O'ZI × partiya va **qo'shilgan** qatorlar × partiya bo'yicha (`required_from_stock`) — bron, yetishmovchilik va TLD shu ta'rifdan o'qiydi; o'zgarmagan qismlar mashina ichida keladi: band qilinmaydi, yetishmovchilikka tushmaydi; yetishmagan **bazaviy model ham TLD ga tushadi** |
| `order` | 25-§6: **yangi model** (tarkibi ham, ombor qoldig'i ham yo'q) — engineer yozgan qatorlar buyurtma ro'yxati EMAS, **spetsifikatsiya**: mol shu tarkibda **BUTUN, BITTA mashina** sifatida ta'minotchidan keladi, alohida butlovchi buyurtma qilinmaydi. `required_from_stock` = faqat bazaviy model × partiya; TLD ga **bitta** qator tushadi, izohida spetsifikatsiya matni; qatorlarga narx kerak emas (narx `base_product.cost_price`da — buyurtmachi yoki import varaqasi kiritadi, 24-to'plam); **`assemble` shart emas** — mashina tayyor holda keladi; `finalize`da qatorlar `Product.specs`ga ko'chadi — model endi oddiy katalog modeli (keyingi safar `build`/`modify` ochiladi, zavod tarkibi `copy_factory_spec` bilan yuklanadi) |

`take`da `mode` berilmasa **avtomatik tanlanadi** (25-§6): tarkibi bor →
`build`; tarkibi yo'q-u omborda bor → `modify`; ikkalasi ham yo'q (yangi
model) → `order`. Shu tufayli 21-§2.5(c) dagi "yangi modelda `modify` erta
bloklanadi" qoidasi endi kamdan-kam ko'rinadi — noto'g'ri rejim
so'ralmaydi, chunki eng boshidanoq to'g'risi taklif qilinadi; aniq
`mode=modify` so'ralsa (masalan frontdan eski so'rov kelsa), guard
bugungidek 400 qaytaradi, xabari `order`ni ko'rsatadi.

**26-to'plam — `order` rejimida narx nazorati.** `order`da qatorlar
spetsifikatsiya, ularning yig'indisi mashinaning narxi EMAS — yetkazib
beruvchi mashinani butun holda, boshqa pulga beradi. Shuning uchun:

- `Configuration.total_price` `order`da `base_product.stock_price`dan
  olinadi (qatorlar yig'indisidan emas); qolgan rejimlarda bugungidek.
- `Configuration.needs_base_price` — modelning o'z narxi yo'qligini
  bildiradi (`order` + `stock_price=0`). Bu `True` bo'lsa: `submit`
  (`ConfigurationViewSet` ham, `deal_submit` ham) 400 bilan to'sadi,
  `finalize` ham 400 qaytaradi — shartnoma **so'ralmagan narx bilan
  ochilmaydi** (sales tasdiqlashidan OLDIN narx joyida bo'lishi shart).
- `request_prices` `order`da MODELNING O'ZINI so'raydi (qatorlarni emas) —
  28-to'plamdagi `PriceRequest` hujjatining bir qatori bo'lib ochiladi.
- Buyurtmachi narx kiritgach (`PriceRequestLine.answer`) `price_arrived`
  zanjirni davom ettiradi — xuddi oddiy butlovchi narxi kelganidek.
- Import model bo'lsa (24-to'plam) `ImportCostSheet` o'rniga endi shu
  yo'lning o'zi ishlaydi — alohida so'rov shart emas.
- 29-§1: yo'l xaritasidagi `price_request` qadami ham `needs_base_price`ni
  bilishi kerak (`items_without_price` `order`da doim bo'sh — 25-§6 — u
  yolg'iz o'zi "narx kerak emas" deb yolg'on "o'tkazib yuborilgan"
  ko'rsatardi, `submit` esa baribir 400 qaytarardi). Ikkalasi endi bir
  xil manbadan gapiradi.

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

**Yetkazish (#2):** chiqim to'lovdan ajratildi. To'lov — pul + sanoq;
mol `POST /contracts/{id}/ship/` da chiqadi. 11-§3: buyurtmachi/bugalter
emas — **sales (shartnoma egasi) va admin**: mijoz bilan gaplashadigan,
molni topshiradigan odam. Bron shu paytgacha ushlab turadi. Balans nol bo'lsa ham yetkazilmaguncha
`completed` emas. Omborda yetmasa: sales `POST /contracts/{id}/
request-procurement/` bilan band qilinmagan qismini buyurtmachiga
yuboradi — kelgan mol aynan shu shartnomaga band qilinadi.

**Partiya (#3):** `Configuration.quantity` — mijoz nechta so'ragani
(zayavkadan ko'chadi). Tarkib bitta dona uchun yuritiladi; yetishmovchilik,
bron, yig'ish va shartnoma partiyaga ko'paytiriladi. Qisman yig'ish yo'q —
hammasi yoki hech nima.

**Texnik tasdiq (#4):** engineer yig'ib bo'lgach `submit` — konfiguratsiya
sales ko'rigiga o'tadi; sales mijozga ko'rsatib `approve` (zayavka `done`)
yoki izoh bilan `reject` (chernovikka qaytadi, engineer xabar oladi).
Ta'minot va yig'ish faqat `approved`dan keyin; `finalize` endi bitta ish —
`approved` + yig'ilgan + ACT bo'lsa `ready` qiladi va shartnoma ochadi.
Ikki xil tasdiq bor: **texnik** (shu tarkib to'g'rimi — konfiguratsiyada)
va **narx** (mijoz summaga rozimi — TLD `pending_sales`).

**Yig'ish qadami (§10.1, 21-§1 bilan yangilangan):** `POST /configurations/{id}/assemble/`
— `build` rejimida tarkib zavod spetsifikatsiyasidan farq qilsa butlovchilar
ombordan chiqadi (kirim YO'Q — variant endi umuman yaratilmaydi); tarkib
zavodnikiga teng bo'lsa (`matching_variant`) yig'ish shart emas, ombor
harakati bo'lmaydi, mol to'g'ridan-to'g'ri bazaviy modelning o'zidan
ketadi. Butlovchi yetmasa `assemble` bloklanadi, engineer
`request-procurement` bilan TLD ochadi; mol kelgach qayta chaqiriladi.
`finalize` — alohida qadam, ACT bilan yakunlaydi, ombor harakatiga
tegmaydi.

**Bron (§11.4):** shartnoma tuzilishi bilan mahsulot **band** (qattiq bron),
konfiguratsiya chernovigi esa **rejada** (yumshoq — to'smaydi, ogohlantiradi).
Chiqim vaqti o'zgarmagan (to'lovda), bron shartnoma–to'lov oralig'idagi oynani
yopadi: yetishmovchilik endi to'lovda emas, shartnoma tuzilayotganda ko'rinadi.
Har amal o'z bronini o'ziga ochiq hisoblaydi. Muddati o'tgan bron
`check_deadlines`da bo'shaydi. 22-§6 (21-§1 regressiyasi tuzatildi): bron
`required_from_stock`dan o'qiydi — tarkib zavodnikiga teng bo'lsa
(`matching_variant`) BAZAVIY MODELGA tushadi, o'zgargan bo'lsa
butlovchilarga (ikkalasi ham bitta ta'rifdan chiqadi, ikki xil haqiqat yo'q).

**Tannarx yangilanishi:** `receive` (TLD ham, KIR ham) har bir qator
uchun mahsulot `cost_price`ini xarid narxi (QQS'siz `unit_price`) bilan
yangilaydi — katalogda narxsiz mahsulot qolmaydi. TLD konfiguratsiyadan
ochilgan bo'lsa, o'sha konfiguratsiyaning narxsiz qatorlari ham kirimdan
keyin avtomatik narx oladi (`needs_price` o'chadi, finalize ochiladi).

**§11 kelishilgan o'zgarishlar (endi kodda):** ACT va `finalize` —
engineerda (§11.1, "Yakunlash va salesga topshirish"); bugalter tasdig'i ikkiga
bo'lindi — "tekshiruv" va "boshlang'ich to'lov" (tarixga `payment` qadami
yoziladi) (§11.2). 12-§1: admin tasdig'i endi bularning O'RTASIDA emas,
Didoxdan **OLDIN** — sales → bugalter → admin → Didox (`didox_number`
`send-didox`da saqlanadi) → to'lov; `admin_approval_threshold` dan
kichik UZS shartnoma admin tasdig'isiz to'g'ridan Didoxga tayyor bo'ladi,
tarixda avtomatik yozuv qoladi, boshqa valyuta doim adminga (§11.3).
Shartnoma va qatorlari tasdiqqa yuborilgach qulflanadi (faqat admin), qator
o'zgarganda `total_amount` avtomatik qayta hisoblanadi (§10.3); rad etilgani
tuzatilib qayta yuboriladi.

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
**YANGI OQIM: shartnoma zanjir boshida.** Zanjir endi `CFG → SHT → pul →
mol` (avval `CFG → mol → SHT → pul` edi):

1. Sales texnik yechimni tasdiqlashi (`approve`) bilanoq **draft shartnoma
   avtomatik ochiladi** (B1; egasi — zayavka sales'i, qator — bazaviy model ×
   partiya, narx — konfiguratsiya narxi). Mijoz aniqlanmasa tasdiq 400 (B10).
2. **Narx shartnomadan oldin** (B2): narxsiz qator `submit`dan o'tmaydi;
   engineer `request-prices` bilan buyurtmachidan narx so'raydi (TLD emas!),
   buyurtmachi tannarxni mahsulot kartasida kiritadi, narx **sales'ga**
   qaytadi. Sotuv narxi yo'q mahsulotda tannarx + `markup_percent` ustama
   (§6-B) qo'llanadi — mijozga tannarxda sotilib ketmaydi.
3. **Bron qoidalari** (B5): molni konfiguratsiya ushlab turadi — unga
   bog'langan shartnoma CFG `ready`/`sold` bo'lmaguncha o'z bronini
   qo'ymaydi (ikki marta band bo'lmasin). Boshlang'ich to'lov kelgach CFG
   broni **yumshoqdan qattiqqa** o'tadi va muddatsiz bo'ladi.
4. `finalize` endi shartnoma ochmaydi — 21-§1 dan keyin qator **bazaviy
   modelda qoladi** (variantga ko'chirilmaydi, chunki variant endi
   umuman yaratilmaydi; son va narx tegilmaydi) va CFG `ready` (pul
   kelgan bo'lsa `sold`) bo'ladi; bron shartnomaga o'tadi.
5. ZVK endi shartnoma `completed` bo'lgandagina arxivlanadi (B7, §3.5) —
   u zanjir umurtqasi bo'lib ro'yxatlarda turadi.
6. **Ta'minot va yig'ish to'lovdan keyin** (B4): `assemble` ham,
   `request-procurement` ham shartnoma `active`/`completed` bo'lmaguncha
   400 beradi ("Boshlang'ich to'lov kutilmoqda — SHT-…"); shartnoma rad
   etilgan bo'lsa — "zanjir to'xtadi". Engineer navbatida to'lov kutayotgan
   konfiguratsiya TURMAYDI — bu uning ishi emas (F8).
7. **Boshlang'ich to'lovdan keyin hech narsa o'zgarmaydi** (B13):
   shartnoma va qatorlari (admin ham!), partiya soni (`change-quantity`),
   zayavka miqdori — hammasi qulflanadi. Ochiq qoladigani: ACT, yig'ish,
   TLD — ish aynan shulardan boshlanadi.
8. **Zayavka miqdori sinxron** (B16 + 6-to'plam §4): sonni **sales**
   belgilaydi — u mijoz bilan kelishadi (engineer tarkib bilan ishlaydi,
   son bilan emas). ZVK `quantity` `new`/`in_progress`/`done` da
   o'zgaradi (chegara to'lovda, zayavka holatida emas) va o'zgarishi
   `change_quantity` orqali o'tadi — konfiguratsiya, bron va (pul
   kelmagan) shartnoma birga yangilanadi; `approved` sales ko'rigiga
   qaytadi.
9. **Aylanma (B15 + 9-to'plam)** — uch xil vaziyat, uch amal:
   **A — rad etish** (`reject`, faqat `new`): zayavkada muammo, engineer
   hali ishga olmagan — `returned`, faqat sales'da, `resend` bilan
   hovuzga qaytadi. **B — aniqlashtirish** (`ask-sales`/`answer`): ish
   borayotganda kichik noaniqlik — konfiguratsiya, tarkib va bron
   JOYIDA qoladi, savol-javob `approvals` tarixida (question/answer).
   **C — qaytarib berish** (`release`, faqat o'zi olgan engineer):
   muammo engineerda (vaqti yo'q) — zayavka `new` ga (hovuzga), CFG
   bekor bo'lib broni bo'shaydi, keyingi `take` toza chernovik ochadi;
   SLA noldan. Har bir qadam `ConfigurationRequestEvent` tarixida.
10. **TLD sales'ga qaytmaydi (10-§4)**: yangi oqimda TLD ochilganda
    hammasi allaqachon bo'lgan (yechim tasdiqlangan, Didox o'tgan,
    TO'LOV KELGAN) — TLD raqamlari bizning xarid tannarximiz, mijoz
    narxi emas. `submit` endi to'g'ridan-to'g'ri bugalterga; sales
    vazifa emas, INFO xabar oladi ("zanjiringiz bo'yicha TLD
    yuborildi"). `pending_sales` va uning approve/reject shoxi jonli
    bazadagi eski hisoblar uchun saqlangan.
11. **Bekor qilish ≠ rad etish (B12/B17)**: `cancel_chain` — zanjir
    O'LADI: SHT/CFG/ZVK `cancelled`, bronlar bo'shaydi, to'lanmagan TLD
    bekor, to'langani ogohlantirish bilan ochiq qoladi (mol baribir
    keladi). Sabab (`reason`) majburiy, tarix va bildirishnomalar
    yoziladi. **Pul qabul qilingan shartnoma bekor qilinmaydi** —
    qaytarish alohida rasmiylashtiriladigan ish. Kim: zanjir egasi
    (sales) yoki admin. Uch kirish nuqtasi — natija bitta.

**Partiya o'zgarishi (4-to'plam §2).** Mijoz sonni o'zgartirsa zanjir
qaytadan boshlanmaydi: `POST /configurations/{id}/change-quantity/` (engineer,
admin; sales so'raydi — §3.4 egalik). Son yangilanadi, bron yangi partiyaga
moslashadi, zayavka (`ConfigurationRequest.quantity`) ergashadi; `approved`
yechim `pending_sales` ga qaytadi — 10 taning narxi 100 taniki emas, mijoz
roziligi qayta olinadi. Rad: mahsulot yig'ilgan (`assembled_at`), terminal
holat, ochiq TLD chernovikdan o'tgan (mol yo'lda — avval TLD hal qilinsin),
`quantity < 1`. Chernovik TLD to'smaydi: buyurtmachi qatorlarni o'zi moslaydi
(xabar oladi). Tarixga `ActivityLog`, zayavka egasiga bildirishnoma.

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

### Narx so'rovi — bitta hujjat, uch rol (28-to'plam, 24-§ o'rnini bosadi)

`request_prices` (engineer, `POST /configurations/{id}/request-prices/`)
narxsiz narsalar (butlovchilar, yoki `order` rejimida bazaviy modelning
o'zi — 26-to'plam) uchun endi **bitta hujjat** — `PriceRequest` —
ochadi; qator (`PriceRequestLine`) — bitta mahsulot. Buyurtmachining (va
import bo'lsa logist/deklarantning) ISH JOYI shu hujjat, mahsulot
kartasidagi tarqoq eslatmalar emas.

**Qator import bo'lsa** (`Product.is_imported=True` yoki so'rovda
`imported_products` bilan shu chaqiruvda birinchi marta belgilansa) — uch
rol ketma-ket ishlaydi va **bir-birining raqamini ko'rmaydi**:

1. **Logist** — jami yetkazish narxi + shundan CHEGARAGACHA qismi
   (`fill-logistics`); tovar narxi, bojxona, tannarx unga ko'rinmaydi.
2. **Deklarant** — TN VED kodi + STAVKA (`duty_percent`, summa emas —
   bojxona qiymatini u ko'rmaydi), aksiz, sertifikat, laboratoriya,
   yig'im, o'z xizmati (`fill-customs`); tovar narxi, logistika, tannarx
   ko'rinmaydi. **Kod mahsulotda BOR va stavka eslab qolingan bo'lsa
   (oxirgi importdan `Product.tnved_code`/`duty_percent`/
   `certificate_cost`/`laboratory_cost` orqali) bu bosqich O'TKAZIB
   YUBORILADI** — qator to'g'ridan logistdan keyin buyurtmachiga tushadi.
   Buyurtmachi shubhalansa `send-to-customs` bilan qaytadan deklarantga
   yuboradi.
3. **Buyurtmachi** — endi ikki bosqichli (30-§2, logist/deklarant naqshi
   bilan bir xil): avval `fill-goods` (tovar narxi — **BITTA DONAGA**,
   valyuta, kurs, ixtiyoriy qo'shimcha xarajatlar) — qatorni YOPMAYDI,
   necha marta ham chaqirilishi mumkin (kurs xato terilgan bo'lsa qayta
   yozadi); tizim shu asosda `suggested_cost`ni ko'rsatadi. Keyin
   `answer` (ixtiyoriy `cost_price`) — bo'sh qoldirilsa `suggested_cost`
   qabul qilinadi, aks holda o'z raqami bilan yakunlanadi. `fill-goods`
   chaqirilmagan import qatorda `answer` — 400. **Mahalliy qator** (import
   emas) — `fill-goods` shart emas, `answer`da `cost_price` majburiy.

Qator holati (`PriceRequestLine.status`, hisoblanadi):
`waiting_logistics → waiting_customs → waiting_supplier → answered`.
So'rov holati (`PriceRequest.status`) — qatorlar orasidan **eng
ORQADAGI** (eng kam bajarilgan) bosqich; aralash so'rovda (mahalliy +
import) har qator o'z yo'lidan yuradi, mos rolga alohida bildirishnoma
boradi.

**Hisob (30-§3 — 24-§2.1/28-to'plamdagi invoys-jami formulasini
almashtiradi)**. Eski formula invoys **jami** summasiga asoslangan edi;
endi buyurtmachi tovar narxini **bitta donaga** kiritadi, hisob ham
donaga chiqadi:

```
declarant_unit = (tovar_narxi_donaga × kurs + sertifikat + laboratoriya + deklarant xizmati) × (1 + duty_percent/100)
logistics_unit = logistics_total / miqdor
extra_unit     = extra_costs / miqdor
suggested_cost = declarant_unit + logistics_unit + extra_unit   (2 xonaga yaxlitlanadi, taklif — yakuniy emas)
```

⚠️ Bu formulada QQS alohida hisoblanmaydi — `duty_percent` yagona
ustama foizi sifatida ishlatiladi (`excise_amount`/`customs_fee`/
`duty_amount` maydonlari bazada tarixiy ma'lumot uchun qoladi, lekin
hisobga kirmaydi). `miqdor=0` bo'lsa `logistics_unit`/`extra_unit` — `0`
(nolga bo'linish yo'q).

Buyurtmachi `answer`da javob berganda: `Product.cost_price` yangilanadi,
`price_arrived` zanjirni davom ettiradi (narxsiz qator/`needs_base_price`
o'chsa CFG sales'ga qaytadi) — bir xil yo'l import va mahalliy uchun
(shu jumladan narx **to'g'ridan `PATCH /products/{id}/` orqali** kelsa
ham — `close_local_price_request_lines_for_product` mahalliy qatorni
avtomatik yopadi, 29-§4a bilan bog'liq emas, lekin shu yo'l bilan bir xil
tamoyil: narx qayerdan kelmasin, kutayotgan hamma joy yopiladi).
Deklarant kod/stavka kiritganda `Product.tnved_code`/`duty_percent`/
`certificate_cost`/`laboratory_cost` ham yangilanadi — keyingi import
uchun eslab qolinadi.

**29-§4: qolgan uchta holat.**

- **Rad etish** (`POST /price-request-lines/{id}/return/`, faqat logist/
  deklarant, `comment` majburiy): "yuk tashiy olmayman" yoki "ma'lumot
  yetmaydi" — qator **mahalliyga aylanadi** (`is_imported=false`,
  tegishli `*_filled_at` tozalanadi), buyurtmachiga "kim va nega
  qaytardi" eslatmasi ketadi. Import yo'lini davom ettirish kerak bo'lsa
  buyurtmachi qaytadan `mark-imported` bosadi.
- **Miqdor o'zgarishi**: `change-quantity` ochiq so'rov qatorlarini ham
  yangilaydi — `quantity` ergashadi, import qatorning **logistika**
  raqami eskiradi (`waiting_logistics`ga qaytadi, logistga eslatma),
  **bojxona STAVKASI saqlanadi** (miqdorga bog'liq emas).
- **Zanjir bekor bo'lishi** (`cancel_chain`, savdodan chiqarish,
  hovuzga qaytarish): ochiq narx so'rovi ham `cancelled` bo'ladi,
  uchala roldagi eslatmalar yopiladi; javob berilgan (`answered`)
  so'rovga tegilmaydi.

> **`ImportCostSheet` (24-to'plam) o'zi saqlanadi** — modeli, hisob-kitobi
> va o'z testlari qoladi, lekin `request_prices` endi uni ochmaydi.
> **29-§6: qo'lda ochish (`POST /import-cost-sheets/open/`) ham olib
> tashlandi** — ro'yxat/detail arxiv/nazorat sifatida qoladi.
> `/api/import-cost-sheets/...` mustaqil endpoint sifatida ishlayveradi
> (masalan qo'lda ochish uchun), yangi importlar esa `PriceRequest`
> orqali yuradi.

## 8. Audit

Har bir yaratish / o'zgartirish / o'chirish / tasdiqlash `ActivityLog` ga tushadi
(`BaseModelViewSet` avtomatik yozadi). Ro'yxat faqat adminga: `GET /api/activity-logs/`.
