# 12 — TZ 2.1 o'zgarishlari (frontend uchun muhim)

TZ v2.1 (27.08.2026) asosida kiritilgan o'zgarishlar. Agar frontend avvalgi versiyaga
qarab boshlangan bo'lsa — shu ro'yxatni tekshirib chiqing.

---

## 1. Yangi rol: Buyurtmachi 🔴 breaking

`User.role` endi **4 xil** qiymat oladi:

```
admin | bugalter | sales | buyurtmachi
```

Rol bo'yicha menyu va tugmalar yig'ilishida `buyurtmachi` qo'shilishi kerak.

**Ta'sir:** rol filtrlari, `RequireRole`, sidebar, `GET /users/?role=`.

---

## 2. Yangi modul: omborni to'ldirish 🆕

17 ta yangi endpoint qo'shildi:

```
GET    /replenishments/low-stock/
POST   /replenishments/from-low-stock/
GET    /replenishments/            POST /replenishments/
GET    /replenishments/{id}/       PATCH, DELETE
POST   /replenishments/{id}/submit/
POST   /replenishments/{id}/approve/
POST   /replenishments/{id}/reject/
POST   /replenishments/{id}/pay/
POST   /replenishments/{id}/events/
POST   /replenishments/{id}/receive/
GET    /replenishments/{id}/timeline/
GET    /replenishment-items/       POST, PATCH, DELETE
GET    /replenishment-approvals/
GET    /replenishment-events/
```

Jarayon: `draft → pending_bugalter → pending_admin → approved → ordered → ... → delivered`

Batafsil: [11-FRONTEND-SCREENS.md §3](11-FRONTEND-SCREENS.md).

---

## 3. Client: yangi majburiy maydonlar 🔴 breaking

Yuridik shaxs formasi o'zgardi:

| Maydon | Avval | Endi |
|---|---|---|
| `mfo` | yo'q edi | **majburiy** |
| `bank_name` | yo'q edi | **majburiy** |
| `account_number` | yo'q edi | **majburiy, unique** |
| `address` | majburiy | **ixtiyoriy** |

Jismoniy shaxs maydonlari o'zgarmadi.

**Ta'sir:** client yaratish/tahrirlash formasi, validatsiya, jadval ustunlari.

---

## 4. Configurator: narxlash mantig'i 🟡

`ConfigurationItem` javobida yangi maydonlar:

| Maydon | Ma'nosi |
|---|---|
| `stock_price` | Ombordagi narx (sotuv narxi, bo'lmasa tannarx) |
| `needs_price` | `true` bo'lsa narx yo'q — yakunlash bloklanadi |

`Configuration` javobida yangi maydonlar:

| Maydon | Ma'nosi |
|---|---|
| `items_total` | Qatorlar yig'indisi |
| `total_price` | Tayyor variant bo'lsa — uning ombordagi narxi, aks holda `items_total` |
| `variant`, `variant_sku` | Yakunlangach yaratilgan/topilgan tayyor pozitsiya |
| `ready_variant` | `{id, sku, price}` yoki `null` — "bu konfiguratsiya omborda bor" |

Yangi xatti-harakatlar:

- `unit_price` yuborilmasa — backend ombordagi narxni qo'yadi
- `POST /finalize/` narxi yo'q qator bo'lsa `400` qaytaradi:
  `{"detail": "Narxi kiritilmagan butlovchilar bor.", "items": ["RAM 4"]}`
- Yakunlangach konfiguratsiya **omborga alohida mahsulot** bo'lib qo'shiladi
  (`sku` = `HP-880-V01`), bir xil tarkib ikkinchi marta yig'ilsa yangi mahsulot yaratilmaydi

`GET /stock-check/` javobiga qo'shildi: `ready_variant`, `variant_price`, `variant_stock`,
`total_price`, har bir qatorda `unit_price` va `needs_price`.

Keyingi aniqlashtirish:

- `POST /configurations/` da `items` **ixtiyoriy** — yuborilmasa zavod tarkibi (specs)
  avtomatik yuklanadi (TZ 6.1: model ichidagi hamma narsa tayyor keladi)
- Tarkib o'zgartirilmagan bo'lsa tizim **bazaviy modelning o'zini** tayyor pozitsiya
  sifatida taniydi: `ready_variant.is_base_model: true`, narx va qoldiq undan olinadi,
  yangi variant yaratilmaydi
- `ready_variant` endi `{id, sku, name, price, stock, is_base_model}` qaytaradi

**Modify rejimi** 🆕 — tayyor mahsulotni o'zgartirish:

- `Configuration.mode`: `build` (default) / `modify`
- `GET /configurations/{id}/changes/` — qo'shilgan/yechilganlar farqi
- `modify` da `finalize` haqiqiy ombor harakatlarini bajaradi: butun mahsulot -1,
  qo'shilganlar ombordan, **yechilganlar omborga qaytadi** (narxi `removals` bilan
  o'zgartiriladi), variant +1; bugalterga ACT bilan eslatma boradi
- Javobda `removals[]` — yechib olinganlar tarixi

---

## 5. Muddat ranglari aniqlashtirildi 🟡

TZ 5.3 dagi misolga (90 kunlik shartnoma) to'liq mos:

| Zona | Avval | Endi |
|---|---|---|
| Sariq | oxirgi 30% (90 kunda: 27 kun) | oxirgi **1/3** (90 kunda: **30 kun**) |
| Qizil | oxirgi 10 kun | o'zgarmadi |

`color` maydoni backendda hisoblanadi — frontend faqat chizadi.

---

## 6. Qarzlar: manba qo'shildi 🟡

`Loan` javobida yangi maydonlar: `source`, `source_display`

| Qiymat | Ma'nosi |
|---|---|
| `personal` | Shaxsiy qarz (kimdandir olingan) |
| `supplier` | Ta'minotchi oldidagi qarz (to'ldirish hisobidan) |

Filtr: `GET /loans/?source=supplier`

Ta'minotchi qarzi muddati — mahsulot omborga kirim qilingan kundan **60 kun**.

---

## 7. Mahsulot: variant maydonlari 🟢

`Product` javobida qo'shimcha: `base_model` (bazaviy model), `signature` (tarkib imzosi),
`stock_price`, `is_variant`.

Variantlar ro'yxati: `GET /products/?kind=machine` — `base_model` to'ldirilgan bo'lsa,
bu Configurator yaratgan tayyor pozitsiya.

---

## 8. Demo ma'lumotlar 🟢

`seed_users` endi **5 ta** foydalanuvchi ochadi (`buyurtmachi` qo'shildi):

| Login | Rol |
|---|---|
| `admin` | Administrator |
| `bugalter` | Bugalter |
| `buyurtmachi` | Buyurtmachi |
| `sales1`, `sales2` | Sales |

Parol: `Ombor2026!` · Komanda: `make docker-demo`

---

## 8.1 Rol ruxsatlari qat'iylashtirildi 🔴 breaking

TZ 8.3 ga muvofiq **sales** endi quyidagi bo'limlarni umuman ocha olmaydi (`403`):

| Bo'lim | Avval | Endi |
|---|---|---|
| Kassa, qarzlar, xarajat so'rovlari | o'qiy olardi | **403** |
| Kirim (`/purchases/`) | o'qiy olardi | **403** |
| To'ldirish (`/replenishments/`) | o'qiy olardi | **403** |
| Ombor (mahsulot, qoldiq, harakat) | **yoza olardi** | faqat o'qiydi |

Ombor yozish endi admin, bugalter va buyurtmachida (avval barcha login qilganlarda edi).

**Frontendga ta'siri:** sales menyusidan Kassa, Kirim va To'ldirish bandlarini olib tashlang;
ombor sahifasida sales uchun "Qo'shish / Tahrirlash" tugmalarini yashiring.
To'liq jadval: [03-ROLES-PERMISSIONS.md](03-ROLES-PERMISSIONS.md).

## 8.1.1 Import hujjatlari 🆕

TZ 2.2 dagi "document" qismi: kirimga fayl biriktirish qo'shildi.

- `POST /purchase-documents/` (multipart) — `purchase`, `kind`, `title`, `file`
- `kind`: `contract` / `invoice` / `customs` / `other`
- Yuklash — bugalter (va admin); buyurtmachi ko'radi; sales — 403
- Kirim javobida `documents[]` ichma-ich keladi

**Frontendga ta'siri:** kirim kartasiga "Hujjatlar" bloki (ro'yxat + yuklash tugmasi
bugalterga) qo'shilsin.

## 8.2 Katalog TZ ga moslandi 🔴 breaking

TZ da mahsulot katalogini boshqarish bo'limi yo'q — shuning uchun:

| Nima | Avval | Endi |
|---|---|---|
| `Category` modeli va `/api/categories/` | bor edi | **butunlay o'chirildi** (TZ da yo'q) |
| `Product.barcode`, `image`, `unit` | bor edi | **o'chirildi** (TZ da yo'q) |
| `POST/PATCH/DELETE /products/` | ochiq edi | **yo'q** (405) |
| `POST /movements/` (qo'lda kirim/chiqim) | ochiq edi | **yo'q** (405) — faqat jarayonlar orqali |
| `/warehouses/`, `/stocks/`, `/product-specs/` yozish | ochiq edi | **yo'q** (405) |

**Yangi mahsulot qanday qo'shiladi:** Buyurtmachi to'ldirish buyurtmasiga qator
qo'shganda — `POST /replenishment-items/` da `product_name` (ixtiyoriy `product_sku`)
yuboriladi va mahsulot katalogga tushadi. Ya'ni **buyurtma qilishning o'zi mahsulot
qo'shish** (TZ 7).

**Frontendga ta'siri:** ombor bo'limida "Mahsulot qo'shish", "Kategoriya" va
"Qo'lda kirim/chiqim" oynalarini olib tashlang. To'ldirish buyurtmasi formasida esa
mahsulot maydoni "bazadan tanlash **yoki** yangi nom yozish" ko'rinishida bo'lsin.

## 8.2.1 Qarz `repaid` xatosi tuzatildi 🐛

Yangi qarzda `repaid` darrov `amount` ga teng chiqar edi (qarz olinganda
yoziladigan **kirim** ham yig'indiga qo'shilardi) — `balance` 0 bo'lib,
ortiqcha to'lovga yo'l ochilardi.

- `repaid` endi faqat **chiqim** (qaytarish) harakatlarini hisoblaydi
- `POST /loans/{id}/repay/` endi tekshiradi: yopiq qarz — `400`,
  musbat bo'lmagan summa — `400`, qoldiqdan ortiq — `400` (+`balance`)

## 8.2.2 Sotuvda ombordan chiqim 🐛→✅

TZ 3.1/9 talab qilgan, lekin yo'q edi: shartnoma bo'yicha **birinchi to'lov
tasdiqlanganda** sotilgan mahsulotlar ombordan chiqim qilinadi
(`StockMovement.reason = sale`, `reference` = shartnoma raqami).

- Omborda yetarli bo'lmasa `confirm-payment` **400** qaytaradi
  (`items[]` — qaysi mahsulot qancha yetmasligi); to'lov ham, kassa ham yozilmaydi
- Keyingi to'lovlar qayta chiqim qilmaydi

**Frontendga ta'siri:** to'lov oynasida 400 kelganda `items[]` ro'yxatini ko'rsating.

## 8.3 Yangi rol: Engineer 🔴 breaking

`User.role` endi **5 xil**: `admin | bugalter | sales | buyurtmachi | engineer`.

Configurator ishlari to'liq Engineerga o'tdi:

| Nima | Avval | Endi |
|---|---|---|
| `/configurations/`, `/configuration-items/` yozish | hamma | **admin, engineer** |
| Sales configuratorda | to'liq ishlardi | faqat ko'radi |

Yangi oqim — matnli zayavka (`/configuration-requests/`, `ZVK-`):

```
sales POST (text) → engineer take → configurator'da tayyorlaydi
→ engineer complete {configuration} → sales'ga notification → shartnoma
```

Demo user: `engineer` / `Ombor2026!`.

**Frontendga ta'siri:** sidebar'da yangi "Zayavkalar" bo'limi; configuratorda
yozish tugmalari faqat engineer'ga; sales'ning konfiguratsiya oynasi zayavka
formasiga almashadi. Matritsalar: [09](09-FRONTEND-REACT.md), [11 §3.5](11-FRONTEND-SCREENS.md).

## 8.4 Zayavka oqimi mustahkamlandi 🐛→✅ (front topgan xatolar)

Frontend integratsiyasida topilgan kamchiliklar tuzatildi:

| Xato | Tuzatma |
|---|---|
| `POST /configuration-items/` → **500** (serializer'da `configuration` yo'q edi) | maydon qo'shildi; endi `configuration` majburiy — bermasangiz **400** |
| Sales zayavka yozganda engineerlar bilmasdi | yaratilganda barcha faol engineerlarga **Notification** tushadi |
| `/configuration-requests/` da `configuration` filtri yo'q edi | qo'shildi: `?configuration=12` |
| `PATCH /configurations/{id}/` `ready`/`attached` da ham ochiq edi | **status qo'riqchisi**: faqat `draft` o'zgaradi, aks holda 400; qatorlar (`/configuration-items/`) ham shunday |
| `take/` konfiguratsiya ocholmasdi (zayavkada model yo'q edi) | quyida 👇 |
| `finalize/` tanadagi `{"act": 2}` ni e'tiborsiz qoldirib 400 berardi | endi qabul qiladi: ACT shu so'rovning o'zida biriktiriladi, oldindan PATCH shart emas; noto'g'ri id — `400 {"act": "topilmadi"}` |

**Zayavkaga `base_product` va `warehouse` qo'shildi** (ikkalasi ixtiyoriy, migration
`0006`). Sales zayavka yozganda modelni tanlab yuboradi — TZ misolining o'zi
"HP 880, lekin SSD 1 TB": model salesga oldindan ma'lum, matn faqat farqni tasvirlaydi.

**`take/` endi chernovik konfiguratsiyani o'zi ochadi:** bazaviy model (so'rov
tanasi > zayavkadagisi), zavod tarkibi avtomatik yuklanadi, `configuration`
maydoni to'ldiriladi va engineer to'g'ri tahrirlashga o'tadi. Tana ixtiyoriy:
`{"base_product": 1, "warehouse": 1, "mode": "build|modify"}`. Model umuman
ko'rsatilmagan bo'lsa — 400.

**Frontendga ta'siri:**
- zayavka formasiga "Bazaviy model" (machine'lar ro'yxati) va "Ombor" selectlari;
- `take` dan keyin javobdagi `configuration` id bilan configurator sahifasiga o'tish;
- `ready` konfiguratsiyada tahrir tugmalarini yashirish (baribir 400 qaytadi);
- engineer dashboardida yangi zayavka notificationlari ko'rinadi.

## 8.5 ACT va yakunlash — sales bosqichiga o'tdi 🔴 breaking

Engineer'ning ishi **faqat configurator tahriri**. Oqim endi shunday:

```
sales zayavka (ZVK) → engineer take → configuratorda tayyorlaydi
→ engineer complete (ACT'SIZ, chernovik holida) → sales'ga notification
→ SALES: ACT yaratadi (POST /acts/) → finalize {"act": id} → ready
→ sales shartnoma tuzadi → bugalter → admin → to'lov
```

| Nima | Avval | Endi |
|---|---|---|
| `POST /acts/` | faqat admin | **sales** (admin) |
| `POST /configurations/{id}/finalize/` | engineer | **sales** (admin); engineer → 403 |
| Engineer `complete` | konfiguratsiya tayyor bo'lishi kutilardi | chernovikni ham qaytaradi — ACT shart emas |

**Frontendga ta'siri:** engineer oynasidan ACT tanlash va "Yakunlash" tugmasi
olib tashlanadi; sales'ning `done` zayavka kartasiga "ACT kiritish + Yakunlash"
bloki qo'shiladi, shundan keyingina "Shartnoma tuzish" ochiladi.

Eslatma: `modify` rejimida yakunlashda ombor tekshiruvi bor — qo'shilayotgan
butlovchi omborda yetarli bo'lmasa `400 {"items": ["GPU 32 (kerak: 4, omborda: 2)"]}`
qaytadi. Bu xato emas, haqiqiy qoldiq nazorati — endi u sales bosqichida ko'rinadi.

## 8.5.1 Bitta ombor — qat'iy qoida 🔴 breaking

Biznesda **BITTA ombor** ishlatiladi, filial degan tushuncha **yo'q**.
Endi bu tizim darajasida majburlanadi:

- **ikkinchi ombor yaratib bo'lmaydi** — model darajasida bloklangan
  (admin panelda ham "qo'shish" tugmasi chiqmaydi);
- demo faqat "Asosiy ombor" yaratadi ("Samarqand filiali" olib tashlandi);
- `warehouse` maydoni endi **hamma joyda ixtiyoriy** — yuborilmasa backend
  yagona omborni o'zi oladi:
  - `POST /configurations/` va `take/`
  - `POST /configurations/{id}/finalize/` (modify)
  - `POST /purchases/`
  - `POST /replenishments/` va `POST /replenishments/from-low-stock/`
  - sotuvda chiqim (`confirm-payment`)
- qoldiq yetmasa xato xabari qaysi ombor tekshirilganini aytadi:
  `"'Asosiy ombor' omborida tayyor HP 880 qolmagan — ..."`.

**Frontendga ta'siri:** barcha formalardan **ombor selectini olib tashlang** —
`warehouse` ni umuman yubormang, backend o'zi hal qiladi. "Omborlar" sahifasi
ham kerak emas (`GET /warehouses/` doim bitta yozuv qaytaradi).

## 8.6 Qo'shimcha to'lov tuzatildi 🐛→✅

Front topgan xato: `POST /contract-payments/` da `paid_at` majburiy edi
(`400 {"paid_at": ["This field is required."]}`) va bu endpoint to'lovni
shunchaki yozib qo'yardi — kassaga tushmasdi, balans yangilanmasdi.

Endi `POST /contract-payments/` ham `confirm-payment` bilan **bir xil**
yo'ldan o'tadi:

- `paid_at` **ixtiyoriy** — yuborilmasa hozirgi vaqt olinadi;
- kassaga `sale` kirimi yoziladi;
- birinchi to'lov bo'lsa muddat sanog'i boshlanadi va mahsulot ombordan chiqadi;
- balans yopilsa shartnoma `completed` bo'ladi;
- `is_prepayment` yuborilmasa servis o'zi aniqlaydi (birinchi to'lov = oldindan);
- tasdiqlanmagan (`draft`/`pending_*`) shartnomaga to'lov — 400.

Minimal so'rov: `{"contract": 10, "amount": "350000000", "method": "cash"}`.

## 8.7 Engineer istalgan tovarni qo'shadi, yetishmagani buyurtmachiga 🆕

**1. Bazada yo'q tovar ham configuratordan qo'shiladi.** Qatorda `component`
o'rniga `new_component_name` (ixtiyoriy `new_component_sku`) yuboriladi —
tovar katalogga butlovchi bo'lib tushadi (TZ 7 uslubi: buyurtma qilishning
o'zi mahsulot qo'shish). Mavjud nom takrorlanmaydi — bor mahsulot olinadi.

```json
POST /api/configuration-items/
{"configuration": 12, "new_component_name": "RAM 32 GB",
 "label": "RAM", "quantity": 2, "unit_price": "900000"}
```

Nested `items` ichida ham ishlaydi (`POST /configurations/`).

**2. Yangi endpoint:** `POST /configurations/{id}/request-procurement/`
(engineer, admin) — omborda yetishmagan qatorlardan **to'ldirish hisobi**
(TLD-, chernovik) ochiladi va konfiguratsiyaga bog'lanadi (`Replenishment.configuration`,
filtr: `GET /replenishments/?configuration=12`). Hammasi omborda bo'lsa — 400.

**3. Xabarlar uchala tomonga boradi** (Notification, warning):

| Kim | Xabar |
|---|---|
| buyurtmachi | kirim qilish kerak — buyurtmani rasmiylashtirib yuboring |
| sales | kirim qilish kerak — mijoz buyurtmasi shu kirimni kutadi |
| bugalter | tekshirib chiqing — buyurtmachi yuborgach tasdiq sizdan boshlanadi |

**4. Keyin mavjud TZ 7 zanjiri ishlaydi:** buyurtmachi `submit` → bugalter
`approve` → admin `approve` → bugalter `pay` (pul yetmasa qarzga) → `receive`
— hammasi `GET /replenishments/{id}/timeline/` line chart bilan kuzatiladi.

**Frontendga ta'siri:** engineer configurator oynasida (a) butlovchi selectiga
"yangi tovar nomi yozish" rejimi; (b) `stock-check` da yetishmovchilik bo'lsa
**"Buyurtmachiga yuborish"** tugmasi — javobdagi TLD raqami bilan to'ldirish
kartasiga havola. Buyurtmachi/sales/bugalter dashboardlarida yangi warning
notificationlar ko'rinadi.

## 8.8 Xavfsizlik va arxitektura audit 🔒

Loyiha xavfsizlik auditidan o'tkazildi, tuzatmalar:

| Nima | Avval | Endi |
|---|---|---|
| SECRET_KEY | zaif default bilan prod'da ham ishlayverardi | `DEBUG=False` da zaif/qisqa kalit — ilova ishga tushmaydi (ImproperlyConfigured) |
| Login brute-force | cheklovsiz | IP bo'yicha **30 urinish/daqiqa** (`/auth/login/`, `/auth/refresh/`) — keyin 429 |
| Fayl yuklash (ACT, kirim hujjati) | istalgan tur/hajm | faqat pdf / rasm / doc(x) / xls(x), maksimal **10 MB** — aks holda 400 |
| Prod cookie'lar | oddiy | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HttpOnly, `X-Frame-Options: DENY` |
| HSTS | yo'q | `DEBUG=False` da 30 kun (`SECURE_HSTS_SECONDS` bilan boshqariladi) |
| Demo parol | kodda qotib qolgan | `.env` dagi `DEMO_PASSWORD` bilan almashtiriladi |
| `finalize` tranzaksiyasi | variant/ombor/status alohida yozilardi | bitta atomic blok — yarim holat qolmaydi |

**Frontendga ta'siri:** login formada 429 kelsa "Urinishlar ko'payib ketdi,
bir daqiqadan keyin qayta urining" deb ko'rsating; fayl yuklashda 400 dagi
`file` xabarini foydalanuvchiga chiqaring.

## 8.9 Ikki xil kirim: Butlovchi va Tayyor model 🆕

Mahsulot ikki turda kirim qilinadi (`Product.kind`): **Butlovchi**
(`component`) va **Tayyor model** (`machine`).

**1. Buyurtmada tur tanlanadi** — yangi tovar qo'shilayotganda
`product_kind` yuboriladi (yuborilmasa `component`):

```json
POST /api/replenishment-items/
{"replenishment": 14, "product_name": "HP 990 kompyuter",
 "product_kind": "machine", "quantity": 2, "unit_price": "18000000"}
```

Javobda `product_kind_display` ("Tayyor model" / "Butlovchi") keladi.

**2. Tayyor model tarkibi (ichidagi configlar)** — `/api/product-specs/`
endi **engineer va buyurtmachi (admin) uchun yoziladigan** bo'ldi (avval hamma
uchun 405). Buyurtmachi tayyor modelni kirim qilganda tarkibini ham kiritadi:

```json
POST /api/product-specs/
{"product": 21, "component": 8, "label": "SSD", "quantity": 2}
```

- bazada yo'q butlovchi: `new_component_name` (+ `new_component_sku`) — katalogga tushadi;
- tarkib faqat `kind=machine` mahsulotga qo'shiladi (butlovchiga — 400);
- takror butlovchi — 400; PATCH/DELETE ham shu rollarda.

**Frontendga ta'siri:** buyurtma qatori modalida "Yangi mahsulot" tabiga
**tur selecti** (Butlovchi / Tayyor model, default Butlovchi); mahsulot
kartasida `kind=machine` bo'lsa engineer uchun "Tarkib qo'shish/tahrirlash"
bloki (`/product-specs/` CRUD).

## 8.10 Mijoz yaratishda 500 tuzatildi 🐛→✅

Front bo'sh inputlarni `""` (bo'sh satr) qilib yuborganda unique+null
maydonlar (`passport`, `company_name`, `inn`, `account_number`, `jshshir`)
bazada `""` bo'lib saqlanardi — ikkinchi mijozda unique to'qnashuv, 500.

Endi bo'sh satr avtomatik **NULL** ga aylanadi (serializer + model.save).
Frontga: bo'sh maydonlarni yuboraverish mumkin, hech narsa o'zgartirish
shart emas.

## 8.11 Kelishuv (Lead): "Keyingi aloqa" eslatmasi 🔔

`next_contact_at` kiritilgan kelishuvda sana kelganda sales'ga avtomatik eslatma:

- kunlik `check_deadlines` endi kelishuvlarni ham tekshiradi;
- **bugun yoki ertaga** aloqa — sariq (warning), **sana o'tib ketgan** — qizil
  (danger, "Aloqa N kun oldin bo'lishi kerak edi");
- eslatma kelishuvni **yaratgan sales'ning shaxsiy** notificationiga tushadi
  (`GET /notifications/?entity=Lead`), boshqalar ko'rmaydi;
- sana kiritilmagan yoki yopilgan (shartnoma tuzildi / yo'qotildi) kelishuvga
  eslatma yozilmaydi; qayta yurganda dublikat yo'q (idempotent).

Front: notificationda `entity='Lead'` kelsa kelishuv sahifasiga havola qilinsin
(13-FRONT-TODO 7-bo'lim).

## 8.12 Bajaruvchi rekvizitlari (CompanyProfile) 🏢

Shartnomani rasmiy shaklda chop etish uchun o'z firmamiz rekvizitlari
backendga qo'shildi — yagona yozuv (singleton, ikkinchi yozuv model
darajasida bloklangan):

- `GET /api/company/` — hamma autentifikatsiyalangan foydalanuvchi o'qiydi;
  yozuv bo'lmasa bo'sh holda o'zi ochiladi;
- `PUT/PATCH /api/company/` — **faqat admin** to'ldiradi va tahrirlaydi
  (sales/bugalter — 403); har bir o'zgarish ActivityLog'ga tushadi;
- maydonlar: `name`, `inn` (STIR), `phone`, `email`, `address`, `bank_name`,
  `mfo`, `account_number`, `director_name`, `contract_terms` (chop etishda
  chiqadigan standart shartlar matni);
- Django admin'da ham bor (ikkinchi yozuv qo'shish tugmasi yashiringan).

Front: 13-FRONT-TODO 8-bo'lim — sozlamalar sahifasi (admin) va shartnoma
chop etish modalida BAJARUVCHI blokini shu endpointdan olish.

## 8.13 QQS (NDS) — shartnoma va to'ldirish qatorlarida 🧾

Hisob-faktura ko'rinishi (Narx · QQS% · QQS · Jami) uchun backend hisob-kitobi:

- `ContractItem.vat_percent` — default **12%** (sozlamada `DEFAULT_VAT_PERCENT`),
  qatorda o'zgartirsa bo'ladi (imtiyozliga 0); `unit_price` — QQS'siz sof narx;
  hisoblanadi: `vat_amount`, `total_with_vat`;
- `ReplenishmentItem.vat_percent` — default **0**: ta'minotchi hisobida QQS
  bo'lsa buyurtmachi foizni o'zi kiritadi;
- hujjat yig'indilari ikkala javobda: `items_total` (Yetkazish, QQS'siz),
  `vat_total` (QQS jami), `items_total_with_vat` (Jami);
- shartnoma `total_amount` endi qatorlardan **QQS bilan** sinxronlanadi —
  oldindan to'lov (30%/15%) va balans mijoz to'laydigan real summadan;
- TLD `total_amount` = QQS bilan qatorlar + logistika + boshqa xarajatlar —
  bugalter `pay` va qarz (shortfall) hisobi shu summadan;
- bugalterdan yashirinadigan qator maydonlari kengaydi: `vat_percent`,
  `vat_amount`, `total_with_vat` ham (TZ: qator narxi faqat sales/admin).

Migratsiyalar: `sales.0002`, `procurement.0003`. Front: 13-FRONT-TODO 9-bo'lim.

## 8.14 Sales-gate: mijoz roziligisiz hisob bugalterga bormaydi ⛔

Muammo: mijoz buyurtmasidan ochilgan TLD hisobi buyurtmachi narx kiritishi
bilan darrov bugalter/adminga tushardi — mijoz hali rozi bo'lmagan bo'lsa
ularning vaqti bekor ketardi.

Endi zanjir hisob turiga qarab:

- **Mijoz buyurtmasidan** (konfiguratsiyadan, `request-procurement` orqali)
  ochilgan hisob: buyurtmachi narx kiritib `submit` → **`pending_sales`** —
  sales'larga notification, sales mijoz bilan kelishib `approve` (yoki mijoz
  rozi bo'lmasa `reject`) → shundan keyingina bugalter → admin → to'lov;
- **oddiy ombor to'ldirish** (konfiguratsiyasiz): eskicha to'g'ridan-to'g'ri
  bugalter → admin — hech narsa o'zgarmadi;
- hammasi omborda bo'lsa TLD umuman ochilmaydi (`request-procurement` 400) —
  engineer `complete` qiladi, sales shartnoma bilan davom etadi; bugalterga
  faqat shartnoma tasdig'i boradi.

Texnik: yangi status `pending_sales`, approval step `sales`, permission
`ProcurementApprovalAccess` (approve/reject — sales/bugalter/admin, bosqichni
servis tekshiradi), sales'ga to'ldirish bo'limi o'qishga ochildi
(migration procurement.0004). Front: 13-FRONT-TODO 10-bo'lim.

## 8.15 Avtomatik shartnoma + chop etish shakli 🖨️

Mijoz bilan oxirgi bosqich: sales finalize qilganda **draft shartnoma o'zi
ochiladi** — bugalterga yuborishdan oldin rasmiy shakl tayyor turadi.

- `POST /configurations/{id}/finalize/` endi tanada `{"client": id}` ham
  qabul qiladi; mijoz berilmasa zayavkadagi (ZVK) mijoz olinadi. Yakunda
  draft shartnoma: qatori — tayyor variant, narxi konfiguratsiyadan, QQS 12%
  bilan, `total_amount` — mijoz to'laydigan real summa. Javobda `contract`
  maydoni. Mijoz aniqlanmasa `contract: null` — sales qo'lda ochadi.
- Yangi endpoint **`GET /contracts/{id}/print/`** (95-endpoint) — chop etish
  shakli uchun hamma narsa bitta javobda: bajaruvchi (`/company/` rekvizitlari),
  buyurtmachi (mijoz, tayyor `display_name` bilan), qatorlar (birlik, narx,
  QQS%, QQS, jami), yig'indilar (Yetkazish/QQS/Jami), oldindan to'lov, shartlar
  matni (`company.contract_terms`). Faqat sales/admin (qator narxlari bor).

Front: 13-FRONT-TODO 11-bo'lim.

## 8.16 Konfiguratsiyada buyurtmachi flagi 🚚

**Muammo (front topdi):** yetishmayotganlar buyurtmachiga yuborilgach
konfiguratsiya sahifasida buni bilib bo'lmas edi — hech qanday status/flag
yo'q, "Buyurtmachiga yuborish" tugmasi yuborilgandan keyin ham turaverardi
(va ikkinchi marta bosilsa yana bitta TLD ochilardi).

**Yechim:**

1. `GET /configurations/` va `/configurations/{id}/` javobida ikkita yangi maydon:
   - `sent_to_procurement` — `true` bo'lsa yetishmayotganlar buyurtmachida va
     jarayon hali tugamagan (badge ko'rsatiladi, tugma yashiriladi);
   - `procurement` — oxirgi TLD hisobi: `{id, number, status, status_display,
     is_open, created_at}`; hech qachon yuborilmagan bo'lsa `null`.
2. `is_open` qoidasi: `cancelled` va `delivered` — yopiq; `rejected` ochiq
   qoladi (buyurtmachi to'g'irlab qayta yuboradi).
3. Takror yuborish blokdan o'tmaydi: ochiq TLD bor bo'lsa
   `request-procurement` **400** qaytaradi (`detail`da mavjud hisob raqami,
   `replenishment`da id).

Front vazifasi: [13-FRONT-TODO.md](13-FRONT-TODO.md) §12.

---

## 8.17 Tasdiq zanjirida bosqich bildirishnomalari 🔔

**Muammo (front topdi):** bugalter TLD hisobini tasdiqlab adminga yuborganda
adminga bildirishnoma tushmas edi — u hisob kelganini bilmay qolardi.
Xabarlar faqat submit (sales'ga) va reject (buyurtmachiga) da bor edi;
shartnoma zanjirida ham xuddi shu kamchilik bor edi.

**Yechim — endi navbat kimga o'tsa, o'sha xabar oladi (`/notifications/`):**

To'ldirish (TLD) zanjiri:

| Amal | Kimga xabar |
|---|---|
| submit (oddiy to'ldirish) | bugalter — "yangi hisob tekshiruvda" |
| submit (mijoz buyurtmasi) | sales — "mijoz roziligi kerak" (avvalgidek) |
| sales approve | bugalter — "bugalter tekshiruvi kutilmoqda" |
| bugalter approve | **admin — "admin tasdig'i kutilmoqda"** (tuzatilgan xato) |
| admin approve | bugalter — "to'lov bosqichi" + buyurtmachi — "to'liq tasdiqlandi" |
| reject (har bosqichda) | buyurtmachi — "hisob qaytarildi" (avvalgidek) |

Shartnoma zanjiri:

| Amal | Kimga xabar |
|---|---|
| sales submit | bugalter — "shartnoma tekshiruvga keldi" |
| bugalter approve | admin — "admin tasdig'i kutilmoqda" |
| admin approve | bugalter — "pul kutilmoqda" + sales (yaratgan) — "tasdiqlandi" |
| reject | sales (yaratgan) — "shartnoma qaytarildi" (izoh bilan) |

Avvalgi umumiy (user'siz, hammaga ko'rinadigan) "admin tasdiqladi" xabari
o'rniga endi aynan ish egalariga yo'naltirilgan xabarlar boradi.

---

## 8.18 pay/confirm-payment: summa satr kelganda 500 tuzatildi 🐛→✅

**Muammo (front topdi):** `POST /replenishments/{id}/pay/` tanasida
`debt_amount` **satr** ko'rinishida (`"500000"`, input'dan odatiy holat)
yoki float kelsa server 500 qaytarardi (satr bilan sonni taqqoslab
bo'lmaydi). `POST /contracts/{id}/confirm-payment/` dagi `amount` da ham
xuddi shu xavf bor edi.

**Yechim:** `core.utils.parse_amount` — summa satr/int/float bo'lsa ham
Decimal'ga o'giriladi:

| Kiruvchi qiymat | Natija |
|---|---|
| `"500000"` (satr) | 200 — qabul qilinadi |
| `500000.5` (float) | 200 — qabul qilinadi |
| `""` yoki yuborilmagan | 200 — summa avtomatik (pay'da shortfall, confirm-payment'da oldindan to'lov) |
| `"abc"` | **400** `{"debt_amount": "Summa noto'g'ri formatda — son yuboring."}` (500 emas) |

Front istalgan formatda yuboraverishi mumkin, lekin tozasi — JSON'da
satr ko'rinishidagi son: `{"debt_amount": "500000"}`.

---

## 8.19 Kirimda xarid narxi katalogga tushadi 🐛→✅

**Muammo (front bug-reporti, TLD-00031):** mol omborga kirim qilinardi,
lekin narxi katalogga tushmas edi — `Product.cost_price` 0 bo'lib
qolaverar, `stock_price` ham 0 berar, configurator qatori `needs_price`
bilan `finalize`ni 400 qilib zanjirni qulflar edi (engineer TLD'dagi
narxni ko'ra olmaydi — 403).

**Yechim:**

1. `inventory.services.update_cost_price` — kirimdan keyin mahsulot
   tannarxi **oxirgi xarid narxi** (QQS'siz qator `unit_price`) bilan
   yangilanadi. 0 yoki manfiy narx mavjud tannarxni buzmaydi.
2. Ikkala kirim yo'lida ham qo'llanadi:
   `POST /replenishments/{id}/receive/` (TLD) va
   `POST /purchases/{id}/receive/` (KIR).
3. Bonus: TLD konfiguratsiyadan ochilgan bo'lsa, o'sha konfiguratsiyaning
   **narxsiz qatorlari kirimdan keyin avtomatik narx oladi** —
   `needs_price` o'chadi, sales hech narsa kiritmasdan yakunlay oladi.

Logistika/boshqa xarajatlar tannarxga taqsimlanmaydi (ular kassa
chiqimida hisoblangan) — tannarx siyosati: oxirgi xarid narxi.

---

## 8.20 BIZNES-LOGIKA auditi: §10 xatolari va §11 kelishuvlari kodda 🚀

Audit hujjati (BIZNES-LOGIKA.md) bo'yicha bitta katta bosqich — uch commit.

### 1-qism — §10 xatolari

| § | Nima tuzatildi |
|---|---|
| §10.1 | **Yig'ish qadami**: `finalize` (build) butlovchilarni chiqarib variantni omborga kiritadi; yetmasa bloklamaydi — yangi `POST /configurations/{id}/assemble/` yoki to'lov oldidan avtomatik. Sotuv endi qulflanmaydi |
| §10.2 | `PATCH /products/{id}/` ochildi (admin/bugalter, yangi `ProductPricingAccess`): `sale_price`, `cost_price`, `reorder_level`, `is_active`. Prays-list bor endi |
| §10.3 | Qator o'zgarganda `total_amount` avtomatik qayta yig'iladi; shartnoma va qatorlari tasdiqdan keyin **qulf** (faqat admin); `rejected` tahrirlanadi va qayta submit bo'ladi; `/contract-items/` da `contract` maydoni tuzatildi (avval 500 edi) |
| §10.4 | `cash_available`/`shortfall` faqat admin/bugalterga (boshqalarga `null`); `/dashboard/` `kassa` bloki ham |
| §10.5 | To'lovda qarz **muzlatiladi** (`debt_amount`) — kassa keyin o'zgarsa ham raqam turadi; qarz yopilganda sanoq to'xtaydi |
| §10.6 | KIR holat qo'riqchisi: faqat oldinga, `received`/`cancelled` — terminal, `received`ga faqat `receive` olib boradi |
| §10.7 | O'lik `attach` endpointi, `Configuration.purchase` FK va `attached` holati olib tashlandi |
| §10.8 | Zanjir yopiladi: to'lovda CFG → **`sold`**, shartnoma ochilganda ZVK → **`archived`**, mijozning ochiq Lead'i shartnomaga bog'lanib `contract` bosqichiga o'tadi |
| §10.9 | `CashTransaction.replenishment` FK — TLD to'lovi endi yetim emas; yacheyka hujjat turidan: UZS → `contract_invoice`, valyuta → `import` |
| §10.10 | `user=null` xabarlar yo'q qilindi: qarz xabari bugalter+adminga, ACT xabari bugalterga |
| §10.12.1 | Xarajat so'rovi faqat **chiqim** yacheykasiga (kirim tanlansa 400) |
| §10.12.3 | `signed_at` bugalter qabulida avtomatik to'ladi |
| §4.3 | **TLD → KIR ulanishi**: TLD `receive` KIR hujjatini avtomatik ochadi (`received`, kassasiz/harakatsiz — hammasi TLD tomonida yozilgan), bugalter invoys/bojxonani shu KIRga biriktiradi; `Purchase.replenishment` FK, TLD ga `exchange_rate` |

### 2-qism — §11.1 / §11.2 / §11.3

| § | Nima |
|---|---|
| §11.1 | **ACT va `finalize` engineerga o'tdi** — "Yakunlash va salesga topshirish" bitta qo'lda; sales ACT'ga 403 |
| §11.2 | Bugalter tasdig'i ikkiga bo'lindi: **Didox qabuli** (`didox_number`, `didox_accepted_at` — approve tanasida) va **boshlang'ich to'lov** (`confirm-payment` endi tarixga `payment` qadamini yozadi) |
| §11.3 | `CompanyProfile.admin_approval_threshold`: shu summadan kichik UZS shartnoma bugalter tasdig'i bilan to'g'ridan-to'g'ri `approved`; tarixda avtomatik admin yozuvi (decided_by bo'sh, sabab bilan); boshqa valyuta doim adminga; 0 — chegara yo'q |

### 3-qism — §11.4 BRON (yangi model `StockReservation`)

`Jami = Band + Rejada + Erkin`. Shartnoma tuzilganda mol **band** (qattiq),
konfiguratsiya chernovigida **rejada** (yumshoq — to'smaydi). To'lovda bron
chiqimga aylanadi; reject — bo'shaydi; muddati o'tsa `check_deadlines`
bo'shatib egasiga xabar beradi (muddatlar admin sozlamasida). Yetishmasa
hujjat to'silmaydi — bor qismi band bo'ladi. Yig'ilmagan variantda bron
butlovchilarga tushadi (§10.1 bilan bitta paket). Har amal o'z bronini o'ziga
ochiq hisoblaydi — to'lov o'z-o'zini bloklamaydi. Yangi endpointlar:
`GET /reservations/`, `POST /reservations/{id}/release/` (admin, sabab
majburiy, auditga tushadi). Mahsulot javobida: `reserved_hard`,
`reserved_soft`, `sellable_stock`, `plannable_stock`; konfiguratsiya qatori
`available` endi "rejadan keyin", xomi — `stock_total`.

Front vazifalari: [13-FRONT-TODO.md](13-FRONT-TODO.md) §13.

---

## 8.21 Bildirishnoma manzillari: hovuz va egalik ajratildi 📬

SIDEBAR-VA-EGALIK spetsifikatsiyasi, A-to'plam. Qoida: **keyingi qadamni
roldagi istalgan odam bajara olsa — hovuz (roldagi har biriga alohida
yozuv); faqat egasi bajara olsa — egasiga.**

| Voqea | Avval | Endi |
|---|---|---|
| Yetishmayotganlar buyurtmachiga ketdi | barcha sales | **zayavka egasi** (topilmasa — barcha sales) |
| Mijoz roziligi kerak (`pending_sales`) | barcha sales | **zayavka egasi** |
| Shartnoma muddati yaqin | `user=None` — hammaga | egasi + bugalter + admin |
| Qarz muddati yaqin | `user=None` — hammaga | bugalter + admin |
| Kirim muddati yaqin | `user=None` — hammaga | bugalter + buyurtmachi |

Texnik o'zgarishlar:

1. **`Replenishment.owner_sales` FK** — zayavka egasi hisob ochilganda
   zanjirdan (`configuration -> requests -> created_by`) bir marta topilib
   yozib qo'yiladi; migratsiya eski hisoblarni ham to'ldiradi.
2. **`Notification.user` endi majburiy** (CASCADE) — "e'lon taxtasi"
   (user=None, hammaga ko'rinadigan) xabar butunlay taqiqlandi;
   `NotificationViewSet` va dashborddan `user__isnull=True` olib tashlandi;
   migratsiya eski egasiz yozuvlarni adminga biriktiradi.
3. `check_deadlines` `_notify` endi bir voqeani bir nechta odamga alohida,
   **per-user idempotent** yozadi.

---

## 8.22 "Menga taqalgan ish" API si va "kim ishlayapti" 📊

SIDEBAR-VA-EGALIK spetsifikatsiyasi, B-to'plam.

**Ikki yangi endpoint, bitta manba** (`apps/core/services.py::collect_work`):

- `GET /my-work/` — bosh sahifa navbati: `{counts, items}`. Har item:
  `section`, `entity`+`id` (havolani front quradi), `number`, `reason` kodi
  (matnni front yozadi: `awaiting_didox`, `client_approval`,
  `fix_and_resubmit`, `assemble`, `track_delivery`, `loan_due`...),
  `amount`, `currency`, `level` (`info`/`warning`/`danger`, danger birinchi).
- `GET /sidebar-counts/` — yon panel: faqat sonlar, faqat COUNT so'rovlari
  (60 soniyalik polling uchun); my-work `counts` bilan ta'rifan bir xil.

Rol bo'yicha nima sanaladi — spetsifikatsiyaning §2.3 jadvali aynan:
sales faqat O'ZINIKI (shartnoma draft/rejected/approved, kelishuv aloqa
sanasi, `pending_sales` hisob — `owner_sales` bo'yicha), engineer `new`
zayavka + o'zi olgani + o'z konfiguratsiyalari (draft + yig'ilmagan ready),
bugalter/admin tasdiq navbatlari, buyurtmachi qoralamalar/yo'ldagilar +
yetishmayotganlar, admin xarajat so'rovlari, bugalter/admin qarz ≤ 10 kun.

**Unumdorlik (§2.4):** `low_stock` Python siklidan bitta SQL annotatsiyaga
o'tkazildi (`low_stock_queryset()` — jami − qattiq bron <= reorder_level);
qarz muddati ham SQL sharti bilan.

**Kim ishlayapti (§5/§6):**

- `User.display_name` (to'liq ism, bo'lmasa username) — `created_by_name`
  endi `Contract` va `Configuration` javoblarida; approvals/zayavka
  serializerlari ham `username` emas, `display_name` qaytaradi.
- `created_by` filtri va saralash: shartnoma, konfiguratsiya, zayavka, TLD;
  TLD da qo'shimcha `owner_sales` (+`owner_sales_name`).
- `GET /users/` o'qish **bugalterga ochildi** (yangi `UserDirectoryAccess`) —
  "Xodim" filtri to'ldiriladi; yozish (rol berish) faqat adminda qoldi.

---

## 8.23 Hujjat egaligi: sales va engineer faqat o'zinikini ko'radi 🔐

SIDEBAR-VA-EGALIK spetsifikatsiyasi, C-to'plam. Obyekt darajasidagi filtr
endi backendda (`get_queryset()`) — UI da yashirish yetarli emas edi:
`GET /contracts/{id}/` va `PATCH` baribir ishlayotgandi.

**Ko'rinish (§3.2 jadvali aynan):**

| Model | sales | engineer | bugalter | admin |
|---|---|---|---|---|
| Shartnoma (+qatorlar, to'lovlar, tasdiqlar) | faqat o'ziniki | — | hammasi | hammasi |
| Kelishuv (Lead) | faqat o'ziniki | — | — | hammasi |
| Zayavka (ZVK) | o'zi yozgani | `new` hammasi + o'zi olgani | — | hammasi |
| Konfiguratsiya (+qatorlar) | o'z zayavkasidan tug'ilgani | faqat o'ziniki | — | hammasi |
| To'ldirish (TLD) | o'z `pending_sales` hisobi | — | hammasi | hammasi (buyurtmachi ham hammasini) |

Boshqaning hujjati endi ro'yxatda chiqmaydi va `GET/PATCH/submit` **404**
qaytaradi — hujjat borligi ham bilinmaydi.

**Tahrir:** yangi `IsOwnerOrAdmin` — yozish faqat egasi va admin (qatorlar
ota-hujjat orqali tekshiriladi); `submit_contract` da xizmat darajasidagi
qo'riqchi ham bor. Egasiz eski yozuvlar bloklanmaydi (admin/bugalter ko'radi).

**Avtomatik shartnoma egasi:** `finalize`ni engineer bossa ham shartnoma
**zayavkani yozgan sales'niki** bo'ladi — aks holda sales o'z shartnomasini
ko'rmay qolardi.

**Zaxira:** admin hammasini ko'radi, tahrirlaydi va sales nomidan yubora
oladi — ta'tildagi xodim ishni qulflamaydi. `reassign` (egasini almashtirish)
keyingi bosqichga yozib qo'yildi.

---

## 8.24 Sales o'z hisobini butun yo'l davomida ko'radi 🐛→✅

TOPSHIRIQLAR #1 (jonli muammo): sales TLD ni tasdiqlashi bilan status
`pending_bugalter` bo'lib, hisob uning ko'zidan yo'qolar edi —
konfiguratsiya kartasidagi TLD nishoni 404 berardi, mijozga "qachon
keladi?" degan savolga javob topib bo'lmasdi.

Endi: sales **o'z** hisobini (`owner_sales=user`) boshidan oxirigacha
ko'radi; boshqa sales'nikini avvalgidek ko'rmaydi — egalik saqlangan.
Egasiz hisob faqat `pending_sales` bosqichida ko'rinadi (oddiy ombor
to'ldirishlari sales'ga tegishli emas). Amal huquqi o'zgarmagan:
approve/reject baribir faqat `pending_sales` da ishlaydi — qolgan
bosqichlarda sales faqat kuzatadi.

---

## 8.25 TLD uchun alohida admin chegarasi ⚡

TOPSHIRIQLAR #2: chegara faqat shartnomada edi — 675 000 so'mlik bitta
protsessor ham admin tasdig'ini kutardi. Bitta chegara ikkalasiga mos
kelmaydi (shartnoma — o'nlab million, butlovchi — yuz minglar), shuning
uchun **ikkinchi maydon**: `CompanyProfile.replenishment_approval_threshold`.

Qoidalar shartnomadagi bilan aynan: taqqoslash QQS+logistika+boshqa
xarajatlar bilan (`total_amount`), faqat UZS (boshqa valyuta doim adminga),
0 — chegara yo'q; chetlab o'tilganda tarixga avtomatik
`ReplenishmentApproval` (step=admin, decided_by bo'sh, sabab bilan);
bildirishnoma "Admin tasdiqladi" demaydi.

Zanjir endi: buyurtmachi → (sales) → bugalter → **summa chegaradan kichik
bo'lsa to'g'ri `approved`** → to'lov.

---

## 8.26 SLA: bir ish kunidan ortiq turgan ish qizil 🔴⏱

TOPSHIRIQLAR #3. Hujjat kimgadir taqalib muddatidan ortiq qimirlamasa —
egasining navbatida ham, adminning bosh sahifasida ham **qizil**.

**Muddat qoidasi** (sozlanadi, `CompanyProfile`):

- `sla_cutoff_hour` (default 16): kesim soatidan **oldin** kelgan ish — shu
  ish kunining oxirigacha; **keyin** kelgani — keyingi ish kunining
  oxirigacha. `sla_working_days` (default 1) — necha ish kuni beriladi.
- Ish kuni — shanba/yakshanba sanalmaydi (Ju 17:00 → muddat Du oxiri).
- Bayramlar hozircha yo'q (keyingi bosqich, jadval kerak bo'ladi).

**`status_changed_at`** — yangi maydon (`StatusTrackedModel`): `Contract`,
`Replenishment`, `ConfigurationRequest`, `Configuration`, `ExpenseRequest`.
Faqat holat haqiqatan o'zgarganda yoziladi (`updated_at` yaroqsiz edi —
izoh tahriri ham yangilardi). Migratsiyada eskilarga `created_at` berildi.

**`/my-work/` kengaydi** (alohida endpoint YO'Q — ikkinchi ta'rif
yozilmasin):

- o'z qatori muddati o'tsa: `level: "danger"` + `waiting_days` (necha ISH
  kuni kutayotgani) — egasi adminga yetguncha o'zi ko'radi;
- adminga qo'shimcha qatorlar: `reason: "stale"`, `holder_role`,
  `holder_name`, `waiting_days` — kimda turib qolgani. Qamrov: shartnoma
  (draft/rejected — sales; pending_bugalter/approved — bugalter), TLD
  (draft/rejected — buyurtmachi; pending_sales — owner_sales;
  pending_bugalter/approved — bugalter), zayavka (new — hovuz;
  in_progress — taken_by), konfiguratsiya (draft — engineer). Adminning
  o'z ishi (pending_admin, xarajat) o'z qatorida qizaradi. `leads`/`loans`
  qamrovda emas (o'z muddati bilan yuritiladi), `active`/`delivered` kabi
  amal kutilmaydigan holatlar ham.
- `sidebar-counts` stale qatorlarni ham sanaydi — raqamlar mos qoladi.

---

## 8.27 Ta'minotchi qarzi endi kassaga "pul" bo'lib tushmaydi 🔴🔴→✅

TOPSHIRIQ-2 #1 (eng og'ir xato): TLD to'lovida yetmagan qism qarzga
o'tganda kassaga `loan` KIRIMi yozilardi — hech qanday pul kelmagan bo'lsa
ham. Natija: kassada qarz summasiga teng **fantom pul** paydo bo'lar (uni
sarflash mumkin edi!), qarz yopilgach esa jami xarajat qarz summasiga
**kam** ko'rsatilardi.

To'g'ri model: ta'minotchi qarzi — **majburiyat** (kreditorlik), kirim
emas. Kassa u bilan faqat qaytarilganda (`loan_repay` chiqimi) uchrashadi.

1. `pay()` qarz qismi uchun kassa yozuvini butunlay yozmaydi (Loan,
   bog'lanish, bildirishnoma — o'z joyida).
2. `LoanViewSet.perform_create` endi `source` ga qaraydi: `personal` —
   kirim bor (pul haqiqatan keladi), `supplier` — yo'q.
3. `Loan.repaid`/`balance` faqat chiqimni sanaydi — test bilan qulflandi.
4. **Migratsiya (finance.0005)** bazadagi fantom kirimlarni o'chiradi va
   logda hisobot chiqaradi (nechta yozuv, jami summa).

⚠️ Deploy'dan keyin **kassa qoldig'i kamayadi** — bu kutilgan natija:
fantom pul yo'qoladi, haqiqiy raqam qoladi (migratsiya logida summa bor).

---

## 8.28 Konfiguratsiyada texnik tasdiq — finalize to'rt ishdan bittaga qisqardi 🔁

TOPSHIRIQ-2 #4. Avval sales mijozga hech narsa ko'rsata olmasdi: "tayyor"
xabari kelganda konfiguratsiya allaqachon yakunlangan, ombor harakatlari
yozilgan va shartnoma ochilgan bo'lardi; ta'minot esa tasdiqlanmagan
yechimga ishlab ketardi.

**Yangi holat mashinasi:**

```
draft ──engineer submit──► pending_sales ──sales approve──► approved
  ▲                              │
  └────────sales reject──────────┘  (izoh bilan — ConfigurationApproval'da)
approved ──assemble──► (yig'ildi) ──finalize──► ready + SHT avtomatik
```

- Yangi model **`ConfigurationApproval`** — texnik tasdiq tarixi (33-model).
- Yangi endpointlar: `POST /configurations/{id}/submit|approve|reject/`
  (submit — engineer; approve/reject — sales, admin). Zayavka ergashadi:
  approve'da `done`, reject'da engineer xabar oladi va chernovik ochiladi.
- **`finalize` endi bitta ish qiladi**: `approved` + **yig'ilgan**
  (`assembled_at`) + ACT bo'lsa `ready` qiladi va shartnoma ochadi —
  mahsulot haqiqatan tayyor bo'lgandagina. Variant yaratish va ombor
  harakatlari **`assemble`ga ko'chdi** (modify rejimi ham: `removals`
  endi assemble tanasida; `act_suggestion` — bajarilgan ishdan tayyor matn).
- **Ta'minot tasdiqdan keyingina**: `request-procurement` `approved`
  bo'lmagan konfiguratsiyada 400 — mijoz rad etsa mol behuda olinmaydi.
- **Engineer kirimdan xabardor** (#4C): TLD `receive` konfiguratsiya
  egasiga "mol keldi — yig'ish mumkin" deb yozadi.
- `complete` endpointi olib tashlandi — uning o'rnini submit/approve oldi
  (tasdiqsiz "tayyor" yo'q). §11.1 dagi "bitta tugma" birlashtirishi
  qaytarildi — sales ko'rish oynasi tiklandi.
- Yumshoq bron endi draft+pending_sales+approved davomida turadi.
- my-work: sales'ga `configuration_review`, engineerга `assemble` /
  `finalize_ready` sabablari; SLA qamroviga pending_sales (sales) va
  approved (engineer) qo'shildi.

---

## 8.29 Konfiguratsiya endi partiya yasaydi (`quantity`) 💯

TOPSHIRIQ-2 #3: mijoz 100 ta so'rasa ham tizim bitta dona yasar edi —
shartnomada 100 yozilib, omborda 1 ta bo'lardi (2-banddagi "to'lovda mol
yetmaydi"ning bosh sababi).

- **`Configuration.quantity`** va **`ConfigurationRequest.quantity`**
  (default 1): sales zayavkada yozadi, `take` konfiguratsiyaga ko'chiradi,
  engineer chernovikda o'zgartira oladi.
- Tarkib qatorlari **bitta dona uchun** o'qiladi; ombor/bron/shartnoma
  bilan ishlashda partiyaga ko'paytiriladi: `shortage` (yangi
  `total_needed`), yumshoq bron, `assemble` (butlovchilar ×partiya chiqadi,
  variant partiya bo'lib kiradi), `modify` (baza ×partiya olinadi, yechib
  olinganlar ×partiya qaytadi — narxi bitta donaga yoziladi), avtomatik
  shartnoma qatori (`quantity=partiya`, narx bitta donaga — jami o'zi
  ko'payadi).
- `total_price` bitta dona narxi bo'lib qoldi — shartnoma `qty × narx`ni
  o'zi hisoblaydi.
- Qisman yig'ish YO'Q (hozircha): hammasi yoki hech nima — yetmasa
  `assemble` 400, mol TLD orqali kelgach butun partiya yig'iladi.

---

## 8.30 Chiqim to'lovdan ajratildi: `ship` + shartnomadan ta'minot 🚚

TOPSHIRIQ-2 #2. Mol to'lov paytida chiqar edi — "90 kun ichida
yetkazamiz" ishlamas, omborda yetmagan shartnoma to'lovda qotib qolar,
undan chiqadigan yo'l yo'q edi (B-holat).

**1-qadam — chiqim endi alohida hodisa:**

- `confirm-payment` faqat pulni oladi: sanoq boshlanadi, `active`,
  mol **chiqmaydi** — bron ushlab turadi. Balans nolga tushsa ham
  **yetkazilmaguncha** `completed` bo'lmaydi (Q5).
- Yangi `POST /contracts/{id}/ship/` — **buyurtmachi/bugalter** (admin):
  mol shu yerda chiqadi, `delivered_at` yoziladi (holat mashinasi
  tegilmadi — Q2), bron `shipped`, balans yopiq bo'lsa `completed`;
  egasiga (sales) "yetkazildi" xabari. Bir marta, to'liq — qisman
  yetkazish yo'q (Q4). 90 kunlik muddat endi to'lovdan yetkazishgacha
  o'lchaydi; `check_deadlines` yetkazilganiga eslatmaydi.
- Buyurtmachi endi faol-yetkazilmagan shartnomalarni ko'radi (yetkazish
  navbati — my-work'da `ship_contract`); SLA qamroviga `active`
  yetkazilmagan shartnoma qo'shildi (buyurtmachida turadi).

**2-qadam — shartnomadan buyurtmachiga:**

- `Replenishment.contract` FK (configuration bilan yonma-yon);
- yangi `POST /contracts/{id}/request-procurement/` — **sales (egasi)**:
  `kerak − band qilingan`dan chernovik TLD, `owner_sales` — shartnoma
  egasi, bitta ochiq TLD qoidasi;
- TLD `submit`da shartnomadan ochilgani ham **sales bosqichiga** boradi;
- `receive()` kelgan molni **shu shartnomaga** band qiladi va egasiga
  "mol keldi — yetkazish mumkin" deb yozadi.

A-holat (katalogda umuman yo'q mahsulot) tegilmadi — u ZVK → engineer
yo'li bilan to'g'ri ishlaydi; shartnoma qatoriga "yangi mahsulot nomi"
yozish ataylab qo'shilmadi.

---

## 8.31 Demo ma'lumotlar yangi oqimlarga qayta yozildi 🌱

`seed_demo` endi so'nggi bosqichlardagi HAMMA mexanizmni jonli ko'rsatadi
(`--reset` eski ma'lumotni o'chirib, toza yuklaydi; userlar qoladi):

- **#4 texnik tasdiq**: 4 konfiguratsiya — chernovik (engineer),
  `pending_sales` (sales ko'rigida), `approved` (ta'minotda) va `sold`
  (to'liq zanjir: submit→approve→assemble→finalize→SHT);
- **#3 partiya**: sotilgan konfiguratsiya 2 talik — assemble 2 ta variant
  yasagan, shartnoma qatori ham 2;
- **#2 yetkazish**: faol shartnoma **yetkazilmagan** (buyurtmachining
  "Yetkazing" navbatida), yana bittasi `ship` bilan yopilgan;
- **§11.3 chegaralar**: profile'da 50 mln (shartnoma) / 5 mln (TLD) —
  bitta katta shartnoma adminга borgan, bitta kichigi va bitta kichik TLD
  admin chetlab o'tilgan (tarixda avtomatik yozuv);
- **owner_sales**: konfiguratsiyadan ochilgan TLD narxlanib
  `pending_sales`da — faqat sales1 xabar olgan;
- **#1 qarz**: 5 mln ta'minotchi qarzi bilan to'lov — kassaga fantom kirim
  YO'Q; shaxsiy qarz esa kirim bilan;
- **§4.3 avto-KIR**: receive'dan KIR hujjati ochilgan;
- **§11.4 bron**: 13 ta faol bron (qattiq — shartnomalar, yumshoq —
  chernovik);
- **SLA**: Didox navbatidagi bitta shartnoma 6 kun "turib qolgan" —
  admin bosh sahifasida qizil, "Bugalterda N ish kuni".

Server yangilangach toza yuklash: `python manage.py seed_demo --reset`.

---

## 8.32 `modify`: tayyor model — yaxlit birlik (`required_from_stock`) 🧩

3-to'plam §1. "Bu konfiguratsiya ombordan nimani oladi?" degan savolga
to'rt joy to'rt xil javob berardi: yig'ish (`finalize_modification`)
to'g'ri (model + qo'shilganlar), bron sinxroni esa BARCHA qatorlarni
band qilardi (mashina ichidagi qismlarni ham), modelning o'zini esa
band qilmasdi; yetishmovchilik va TLD ham qatorlardan hisoblanardi.
Natija: yo'q narsa band, kerakli narsa ochiq, 10 ta tayyor model esa
istalgan paytda sotilib ketishi mumkin edi — yig'ish 400 berardi.

- `Configuration.required_from_stock` — yagona ta'rif: build — har bir
  qator × partiya; **modify — bazaviy modelning O'ZI × partiya + faqat
  qo'shilgan qatorlar × partiya**. O'zgarmagan qismlar ombor bilan
  umuman ishlamaydi;
- `sync_configuration_reservations` shu ro'yxatdan quradi — endi
  **modelning o'zi band qilinadi**, ichidagi qismlar band qilinmaydi;
- `missing_items` shu ro'yxatdan: `{product, needed, available,
  shortage}` — yetishmagan **bazaviy model ham ro'yxatda**;
- `request-procurement` TLD ga endi bazaviy model qatori ham tushadi
  (`ReplenishmentItem` mashinani allaqachon qabul qilardi) — TLD kirim
  qilingach yig'ish o'tadi (avval model kelmagani uchun o'tmasdi);
- `finalize_modification` qo'riqchisi ham shu ta'rifdan o'qiydi
  (mantiq o'sha: model va qo'shilganlar tekshiriladi, xabar `items`
  ro'yxati bilan);
- build rejimida xulq o'zgarmagan.

Testlar: `apps/configurator/tests/test_required_from_stock.py` (7).

---

## 8.33 Javobda `missing` — "Yig'ish" yoki "Buyurtmachiga yuborish" 🔘

3-to'plam §2. Yetishmovchilik bo'lganda "Yig'ish" tugmasi baribir 400
berardi — endi front qarorni uchta joydan yig'ib emas, bitta maydondan
oladi. Konfiguratsiya javobiga `missing` ro'yxati qo'shildi:
`{product, name, kind, needed, available, shortage}` — `required_from_stock`
dan quriladi (§8.32), modify'da bazaviy model ham shu yerda (`kind`:
`machine`/`component`). `missing_count` endi shu ro'yxat uzunligi
(avval `items` dan hisoblanib modify'da noto'g'ri son berardi).

Front qoidasi: `missing` bo'sh — "Yig'ish", bo'sh emas — "Buyurtmachiga
yuborish · N". Alohida endpoint ochilmadi: bazaviy model va butlovchilar
BITTA TLD da ketadi (`open_replenishment` — bitta ochiq hisob qoidasi).

---

## 8.34 `available` manfiy chiqmaydi — o'rniga `overbooked` 🧮

3-to'plam §3. Boshqa hujjat bron qilgan mol keyin chiqim bo'lib ketsa
reja qoldig'i manfiyga tushar va ekranda "omborda -6" degan tushunarsiz
raqam chiqardi. Endi (`ConfigurationItem.available` ham, `missing`
ro'yxati ham):

- `available` — 0 dan past tushmaydi;
- `overbooked` — boshqa hujjatlarga zaxiradan ortiqcha va'da qilingani
  (yangi maydon, tarkib qatorlarida ham, `missing` da ham);
- `shortage` xom qoldiqdan hisoblanadi — teshikni ham yopadi: 10 tasi
  o'ziga + 6 tasi teshikka = 16 (buyurtma to'g'ri, ko'rinishi endi aniq).

---

## 8.35 To'lov qoldiqdan oshmaydi — kassaga yo'q pul yozilmaydi 💰

4-to'plam §3 (2-to'plam §1 bilan bir turdagi xato). To'lov summasida
yuqori chegara yo'q edi: jonli SHT-00036 da 9 296 000 lik shartnomaga
653 508 800 yozilib, kassa yolg'on kirim bilan oshgan, balans manfiyga
tushgan edi. Endi `confirm_payment` da (ikkala yo'l — `confirm-payment`
va `POST /contract-payments/` — shu servisdan o'tadi):

- `amount <= 0` — 400;
- `amount > balance` — 400, kassaga hech nima yozilmaydi; ortiqcha
  to'lov shartnomaning ishi emas (qaytarish/avans alohida hujjat);
- balansi manfiy eski shartnomalarda chegara `max(balance, 0)` —
  ular 500 emas, tushunarli 400 oladi;
- `confirm-payment` da ANIQ `0` yuborilsa endi default (oldindan
  to'lov) olinmaydi — 400 (avval `amount or ...` nolni "yuborilmagan"
  deb chalkashtirardi).

Testlar: `apps/sales/tests/test_payment_limit.py` (5).

---

## 8.36 Partiya sonini o'zgartirish — `change-quantity` 🔢

4-to'plam §2. Mijoz "10 emas, 100 kerak" desa yagona chora
konfiguratsiyani bekor qilib qaytadan boshlash edi (tasdiq tarixi, TLD,
zayavka bog'lanishi — hammasi yo'qolardi): `quantity` faqat chernovikda
tahrirlanadi. Endi:

- `POST /configurations/{id}/change-quantity/` —
  `{"quantity": 100, "comment": "..."}`; **engineer** (hujjat egasi) va
  admin — sales so'raydi, engineer yozadi (§3.4 egalik);
- holatlar: `draft` / `pending_sales` / `approved`;
- son yangilanadi, **bron** `required_from_stock` × yangi partiya bo'yicha
  qayta quriladi, **zayavka soni** ergashadi (ikki hujjatda bir xil son);
- `approved` bo'lsa **`pending_sales` ga qaytadi** — bu tijoriy
  o'zgarish: narx va muddat mijoz bilan qayta kelishiladi (sales
  navbatiga `configuration_review` qatori o'zi qaytadi);
- rad: yig'ilgan (`assembled_at` — ombor harakatlari yozilgan), terminal
  holat, **ochiq TLD chernovikdan o'tgan** (400 xabarida TLD raqami) —
  chernovik TLD esa to'smaydi, buyurtmachiga xabar boradi;
- tarixga `ActivityLog`, zayavka egasiga (sales) bildirishnoma.

Testlar: `apps/configurator/tests/test_change_quantity.py` (6).

---

## 8.37 Eski bronlarni tozalash — `resync_reservations` 🧹

4-to'plam §1. 3-to'plam §1 kelajak uchun to'g'ri ishlaydi, lekin undan
OLDIN yozilgan bronlar eski qoida bilan qolgan edi (jonli bazada 125
dona "mashina ichidagi" butlovchi behuda qulflangan, modellar esa
ochiq). O'zi tuzalmaydi: saqlash faqat chernovikda o'tadi, TLD kirimi
hisobi bor hujjatnigina tuzatadi, finalize esa zanjir oxiri.

- `python manage.py resync_reservations` — har bir konfiguratsiya
  uchun `sync_configuration_reservations`: ochiq holatlar
  (`draft`/`pending_sales`/`approved`) `required_from_stock` bo'yicha
  qayta band qilinadi, terminal holatlar (`ready`/`sold`/`cancelled`)
  bo'shatiladi; hisobot chiqaradi;
- Makefile: `make resync` (lokal) / `make docker-resync` (server);
- migratsiya emas, komanda: bron ta'rifi yana o'zgarsa qo'lda bir
  marta yurgizib qo'yiladi.

**Serverda deploydan keyin bir marta:** `make docker-resync`.

Testlar: `apps/core/tests/test_resync_reservations.py` (2).

---

## 8.38 Eslatmalar endi tozalanadi 🔔

4-to'plam §4. Jonli bazada hech kimning eslatmasi hech qachon
yopilmagan (sales1: 28/28 o'qilmagan) — qo'ng'iroqchadagi son "sizga
N marta xabar berilgan" degan ma'nosiz raqam edi. Ikkita mustaqil qism:

- **A.** `POST /notifications/mark-all-read/` — o'zining barcha
  o'qilmaganlarini bittada yopadi (`{"updated": N}`); queryset o'z
  eslatmalari bilan cheklangan, bitta UPDATE;
- **B.** ish bitganda eslatma o'zi yopiladi:
  `resolve_notifications(entity, object_id, user=...)` har bir o'tish
  amalida chaqiriladi — `contract.approve/reject/confirm-payment/ship`,
  `configuration.approve/reject/assemble/finalize`,
  `replenishment.approve/pay/receive`. Faqat **ishni bajargan odamning**
  eslatmasi yopiladi — o'sha hujjat haqida boshqalarga ketgani turadi;
- bonus: `/notifications/` da `object_id` filtri — "shu hujjat bo'yicha
  xabarlar" ko'rinishini chizish mumkin.

Front hujjat ochilganda o'zi yopa olmasdi: hujjatni ochish ishni
bajarish degani emas, filtrda `object_id` ham yo'q edi.

Testlar: `apps/core/tests/test_notifications_cleanup.py` (5).

---

## 8.39 YANGI OQIM 1-bosqich: shartnoma zanjir boshida 🔄

YANGI-OQIM hujjati (B1, B2, B5, B6, B9, B10, §6-B). Zanjir yo'nalishi
teskari bo'ldi: `CFG → mol → SHT → pul` o'rniga **`CFG → SHT → pul → mol`**.

- **B1**: `approve_configuration` da draft SHT avtomatik ochiladi (egasi —
  zayavka sales'i); `finalize` endi shartnoma ochmaydi;
- **B10**: mijoz aniqlanmasa tasdiq 400 — shartnoma majburiy bo'g'in;
- **B2**: narxsiz qator `submit`dan o'tmaydi (nol qatorlar avval ombordan
  qayta o'qiladi); yangi `POST /configurations/{id}/request-prices/` —
  buyurtmachiga eslatma (TLD emas), takrorida yangilanadi; buyurtmachi
  endi mahsulot kartasida narx kirita oladi (`ProductPricingAccess` +
  SUPPLIER); narx kirgach qatorlar to'ladi, eslatma yopiladi va **sales**
  xabar oladi;
- **§6-B (ochiq savolga tavsiya bo'yicha B varianti)**:
  `CompanyProfile.markup_percent` — sotuv narxi yo'q mahsulotda
  `stock_price = tannarx + ustama`; default 0 (xulq o'zgarmagan, admin
  Sozlamalarda yoqadi) — mijozga tannarxda sotilmasin;
- **B5**: konfiguratsiyaga bog'langan SHT, CFG `ready`/`sold`
  bo'lmaguncha bron qo'ymaydi (ikki marta band yo'q, §3.2); to'lov
  kelgach CFG broni **HARD** va muddatsiz; `plannable`/`sellable` o'z
  qattiq bronini o'ziga ochiq hisoblaydi;
- **B6**: `finalize` shartnoma qatorini yig'ilgan variantga ko'chiradi
  (son/narx tegilmaydi) + `ActivityLog`;
- **B7 (qisman)**: ZVK endi SHT `completed` bo'lganda arxivlanadi;
  finalize'da SHT `active` bo'lsa CFG `sold`;
- **B9**: `ConfigurationSerializer.contract` — {id, number, status,
  total_amount, prepayment_amount, paid, **is_paid**};
- to'lovda engineerga "ish boshlanadi" xabari (B5.3).

Migratsiya: `core.0007` (markup_percent). Endpoint: 106 → 107.
Testlar: `test_contract_first.py` (7) + eski oqim testlari yangi zanjirga
moslandi. **Diqqat: ta'minot/yig'ishning to'lov qulfi (B4/B13) keyingi
bosqichda** — servergacha 2-bosqich bilan birga chiqariladi.

---

## 8.40 YANGI OQIM 2-bosqich: hamma ish to'lovdan keyin 💳

YANGI-OQIM B4, B13, B16 (§7 talabi: 1-bosqich bilan bitta relizda).

- **B4**: `assemble` va `request-procurement` endi shartnoma
  `active`/`completed` bo'lishini talab qiladi — 400 "Boshlang'ich to'lov
  kutilmoqda — SHT-…" (rad etilgan/bekor qilinganida "zanjir to'xtadi");
  engineer navbatida to'lov kutayotgan konfiguratsiya turmaydi, admin SLA
  ham u bosqichni shartnoma qatorida (bugalterda) ko'radi;
- **B13**: to'lovdan keyin HECH NARSA o'zgarmaydi — shartnoma/qatorlari
  (`active`/`completed`da admin ham tahrirlay olmaydi), partiya
  (`change-quantity` 400), zayavka miqdori. Pul kelmagan draft shartnoma
  esa partiya o'zgarishiga ergashadi (qator soni + jami qayta yig'iladi);
- **B16**: ZVK `quantity` faqat `new`/`in_progress` da o'zgaradi
  (keyin 400); o'zgarish `change_quantity` orqali o'tadi — bitta mantiq:
  konfiguratsiya, bron, shartnoma va ZVK birga yangilanadi (sales o'z
  zayavkasida, engineer hammasida);
- bron aniqliklari: `active`-yetkazilmagan shartnoma broni endi QO'YILADI
  va muddatsiz (avval `active` umuman sync qilinmasdi — §3.2 dagi "pul
  to'langan shartnoma omborni ushlamayapti" teshigi yopildi); yig'ish va
  ship o'z zanjirining QATTIQ bronini o'ziga ochiq hisoblaydi;
- seed_demo yangi tartibda: A-hikoya to'lovni yig'ishdan OLDIN oladi,
  D-hikoya TLD'dan oldin to'lov zanjirini yuradi.

Testlar: `apps/configurator/tests/test_payment_gates.py` (8).

---

## 8.41 YANGI OQIM 3-bosqich: aylanma va bekor qilish 🔁

YANGI-OQIM B15, B12, B17. §2.1 aylanmasining kodda yo'q ikkita chiqish
yo'li ochildi, "hammasini bekor qilish" esa birinchi marta paydo bo'ldi.

- **B15**: `ConfigurationRequest.Status.RETURNED` + yangi model
  `ConfigurationRequestEvent` (created/taken/returned/resent/price_asked/
  price_given/cancelled/note — TLD timeline'i bilan bir xil shakl);
  `POST /configuration-requests/{id}/reject/` (engineer, izoh majburiy,
  `new` va `in_progress`da; CFG bekor bo'lib broni bo'shaydi) va
  `POST .../resend/` (sales egasi — hovuzga qaytadi). `returned` faqat
  sales ro'yxatida — boshqa engineer olib qo'yib izoh o'qilmay qolmasin;
- **B12/B17**: `cancel_chain(document, user, reason)` — uch kirish
  nuqtasi (`/contracts/{id}/cancel/`, `/configurations/{id}/cancel/`,
  `/configuration-requests/{id}/cancel/`), natija bitta: SHT/CFG/ZVK
  `cancelled`, bronlar `released`, to'lanmagan TLD bekor, to'langani
  "ochiq qoladi — mol baribir keladi" ogohlantirishi bilan tegilmaydi;
  zanjirning ochiq eslatmalari yopiladi, qatnashchilarga bitta xabar;
  **pul qabul qilingan shartnoma bekor qilinmaydi (400)**; kim — zanjir
  egasi (sales) yoki admin; sabab majburiy;
- zayavka javobida `events[]` tarix keladi (front timeline chizadi).

Migratsiya: configurator.0012. Endpoint: 107 → 112. Model: 33 → 34.
Testlar: test_request_loop.py (5), test_cancel_chain.py (5).

---

## 8.42 YANGI OQIM 4-bosqich: Didox ikki qadam + foiz quli 📝

YANGI-OQIM B3, B14.

- **B3**: Didox endi uch harakat — ko'rdi → **Didoxga yubordi**
  (`POST /contracts/{id}/send-didox/`, `didox_number` majburiy, yangi
  holat `pending_didox`, yangi maydon `didox_sent_at`) → **Didox
  tasdiqladi** (`POST /contracts/{id}/confirm-didox/`,
  `didox_accepted_at` o'z haqiqiy ma'nosini oldi — mijoz imzoladi);
  keyin §11.3 chegara mantig'i (`pending_admin`/`approved`).
  `ContractApproval.Step`ga `didox` qo'shildi — tarix uzilmaydi.
  Didox rad javobi ataylab kiritilmagan (kelishuv): mijoz Didoxning
  o'zida qayta yuboradi, `pending_didox`dan orqaga yo'l yo'q.
  B11 mosligi: eski bitta qadamli `approve` (pending_bugalter'dan)
  ishlayveradi. Bugalter navbatida ikkita yangi qator: `send_to_didox`
  (warning) va `didox_confirm` (info — tashqi kutish);
- **B14**: `prepayment_percent` faqat `draft`/`rejected` da
  o'zgartiriladi — bugalterga ketgach (admin ham) 400. Default avval
  qo'yiladi (30%/15%), sales qoralama oynasida tuzatadi;
- seed_demo Didox qadamlarini ikki qadam bilan yuradi.

Migratsiya: sales.0006. Endpoint: 112 → 114.
Testlar: `apps/sales/tests/test_didox_steps.py` (6).

---

## 8.43 YANGI OQIM 5-bosqich: roadmap + ma'lumot ko'chirish 🗺️

YANGI-OQIM B8, B11 — hujjatdagi oxirgi backend bosqichi.

- **B8 — roadmap**: `GET /configuration-requests/{id}/roadmap/`,
  `GET /configurations/{id}/roadmap/`, `GET /contracts/{id}/roadmap/` —
  uchchalasi ham BIR XIL javob (zayavka topiladi, butun zanjir chiziladi).
  18 qadam doim to'liq va tartibda; har qadamda `label`, `state`, `tone`
  (SLA — mavjud `sla_deadline`/`working_days_since`dan, yangi hisob yo'q),
  `actor` (ism+rol; kelajak qadamda faqat rol), `waiting_days`/`deadline`
  tayyor, `document` raqami, `can_open` (§3.13 matritsasi backendda),
  `repeats` (aylanma). Ko'rinish qoidasi hujjatlarnikiga bo'ysunmaydi —
  beshala rol ham to'liq ko'radi; evaziga **javobda pul yo'q** (qat'iy
  chegara). Manba: statuslar + `ContractApproval`/`ConfigurationApproval` +
  `ConfigurationRequestEvent` (B15) + Didox maydonlari (B3);
- **B11 — ko'chirish**: `python manage.py migrate_to_contract_first
  [--dry-run]` — shartnomasiz `approved` konfiguratsiyalarga draft SHT
  ochib beradi (mijozsizlarini ro'yxatlab beradi — sales qo'lda
  bog'laydi); `pending_bugalter` shartnomalar eski bitta qadamli
  `approve` bilan o'taveradi. Makefile: `make contract-first` /
  `make docker-contract-first`.

**Serverda deploydan keyin bir marta:** `make docker-contract-first`
(va 4-to'plamdagi `make docker-resync` hali yurgizilmagan bo'lsa — u ham).

Endpoint: 114 → 117. Testlar: `apps/core/tests/test_roadmap.py` (7).
Shu bilan YANGI-OQIM hujjatining B1–B17 backend topshiriqlari TO'LIQ
yopildi — front ishlari (F1–F11) endi boshlanishi mumkin.

---

## 8.44 6-to'plam: shartli roadmap qadamlari + son sales'da 🎯

6-to'plam (§1–§4).

- **§1/§2 — shartli qadamlar**: `price_request` chernovikda noto'g'ri
  `current` bo'lib turardi (narx so'ralmagan bo'lsa ham). Endi to'rt
  shartli qadam (`price_request`, `admin_approve`, `procurement_sent`,
  `procurement_chain`) `optional: true` bilan keladi va `current`ni
  faqat ish haqiqatan boshlanganda oladi (narx so'ralgan — kutilmoqda;
  TLD ochiq — buyurtmachida). Shart aniq bo'lmasa `skipped`: narxsiz
  qator yo'q, `missing` bo'sh (yoki yig'ilgan), summa chegaradan past —
  admin qadami endi shartnoma ochilishi bilanoq skipped;
- **§3**: joriy qadam tanlashda override birinchi tekshiriladi —
  `current_key` hech qachon skipped qadamga ishora qilmaydi;
- **§2.1** — rol linzasi frontda hal qilindi (backend javobi bitta,
  o'zgarmaydi);
- **§4 — sonni sales belgilaydi**: `change-quantity` endi **sales**
  (admin) uchun — engineer 403 (rol taqsimoti teskari edi); ZVK orqali
  yo'l ham ochiq va `done` holatda ham ishlaydi (`QUANTITY_EDITABLE` +
  DONE) — chegara to'lovda: `approved`dagi o'zgarish yechimni sales
  ko'rigiga qaytaradi, to'lovdan keyin baribir 400 (B13).

Testlar: test_roadmap.py +4 (11), payment_gates/change_quantity
yangilandi.

---

## 8.45 7-to'plam: bosh sahifa uchun zanjirlar ro'yxati 🏠

7-to'plam §1 (bloklovchi — front bosh sahifani shu endpointga quradi).

- `GET /roadmaps/?state=open&limit=10` — joriy foydalanuvchi
  qatnashayotgan zanjirlar, har biri detal `roadmap` javobi shaklida
  (front `Roadmap` komponentini o'zgarishsiz ishlatadi);
- qatnashish: hujjat egasi YOKI joriy qadam uning rolida (bugalter va
  buyurtmachi hech qanday hujjatni ro'yxat qilib ololmasdi — endi
  navbati kelgan zanjirni ko'radi); admin — hammasi;
- tartib: muddatdan o'tgan → navbati shu foydalanuvchida → kutish
  vaqti; `state=open/closed/all`, `limit` 1–50;
- front: `WorkQueue` va "Eslatmalar" kartasi o'rniga `ChainList`
  (eslatmalar qo'ng'iroqchada qoladi). Ochiq savol (hujjatdagi):
  admindagi `EscalationQueue` taqdiri — yangi ro'yxat muddatdan
  o'tganlarni birinchi ko'rsatadi; `/my-work/` backendda o'z joyida
  qoladi, qarorni front/admin keyin beradi.

Endpoint: 117 → 118. Testlar: `apps/core/tests/test_roadmap_list.py` (6).

---

## 8.46 8-to'plam: zanjir shakli, yagona shartnoma, bekor sababi 🧷

8-to'plam (§1, §3, §4; §2 — kuzatuv sifatida qayd etildi).

- **§1**: roadmapda zanjirda UMUMAN bo'lmaydigan hujjat qadamlari endi
  `skipped` — qo'lda ochilgan shartnoma (ZVK/CFG yo'q) "Zayavka
  yozildi"da turib qolardi, endi joriy qadam to'g'ri (mas. `completed`).
  Qoida: keyingi bosqich hujjati bor-u, oldingisi yo'q — oldingisi endi
  hech qachon paydo bo'lmaydi (frontda ajratib bo'lmasdi);
- **§2 (kuzatuv)**: yetkazilgan-u balansi ochiq shartnoma `state=open`da
  qoladi — ataylab: qoldiq to'lovi ham kimningdir ishi;
- **§3**: bitta konfiguratsiyaga BITTA shartnoma — `ContractSerializer`
  endi `configuration` bilan ikkinchisini 400 qiladi (bekor qilingani
  hisobga olinmaydi); avtomatik yo'l allaqachon himoyalangan edi, endi
  qo'lda POST ham; qo'lda tuzish ombordan to'g'ridan-to'g'ri sotuvniki;
- **§4**: `Configuration.cancel_reason` — "nega to'xtadi?" javobi
  hujjatning o'zida: `reject_request` (engineer izohi) va `cancel_chain`
  (sabab) ikkalasi ham to'ldiradi; serializer'da o'qiladi. Sales rad
  etilgan konfiguratsiyani ko'rmasligi (404) — tanlangan yo'l (№1):
  unga zayavkadagi `returned` izohi yetarli.

Migratsiya: configurator.0013. Testlar: test_chain_shapes.py (5).

---

## 8.47 9-to'plam: rad etish ≠ aniqlashtirish ≠ qaytarib berish 🔀

9-to'plam (§1, §2). B15 da uchta boshqa-boshqa ish bitta amalga qo'shib
yuborilgan edi — ishga olingan zayavka qaytarilganda engineer'ning
soatlab ishi (konfiguratsiya) yo'q qilinardi.

- **§1A**: `reject` endi FAQAT `new` zayavkada — ishga olinganida 400;
- **§1B — aniqlashtirish**: yangi holat
  `Configuration.PENDING_CLARIFICATION` va ikki endpoint —
  `POST /configurations/{id}/ask-sales/` (engineer savoli, izoh
  majburiy) va `POST /configurations/{id}/answer/` (sales javobi).
  Konfiguratsiya, tarkib va BRON joyida qoladi; suhbat
  `ConfigurationApproval`da (yangi step `engineer`, decision
  `question`/`answer` + `ordering=created_at`) — "Tasdiqlashlar"
  ro'yxati ikki tomonlama suhbatga aylanadi. Roadmapda alohida qadam
  YO'Q (aylanma): joriy `submitted`ligicha qoladi, lekin actor —
  sales ("kim kutilmoqda" javobi), savollar soni `repeats`da;
- **§2 — hovuzga qaytarish**: `POST /configuration-requests/{id}/release/`
  — muammo zayavkada emas, engineerda (vaqti yo'q); faqat o'zi olgan
  engineer (admin), izoh majburiy; zayavka `new` ga (RETURNED emas —
  sales'da tuzatadigan narsa yo'q), CFG bekor (`cancel_reason`), bron
  bo'shaydi; hovuz (o'zidan tashqari) + sales xabar oladi; yangi event
  `RELEASED`; roadmap `taken.repeats` endi RETURNED+RELEASED; SLA
  noldan boshlanadi — yangi engineer eskisining kechikishida aybdor
  emas;
- sales navbatida yangi qator `clarification_answer`, admin SLA'da
  `pending_clarification` egasi — sales; bron ushlab turiladigan
  holatlarga `pending_clarification` qo'shildi.

Migratsiya: configurator.0014, 0015. Endpoint: 118 → 121.
Testlar: test_request_loop.py qayta qurildi (8).

---

## 8.48 10-to'plam §1–2: narx so'rovi buyurtmachiga yetadigan bo'ldi 💬

Narx so'rovi eslatmasi konfiguratsiyaga ishora qilardi — buyurtmachi uni
ocholmasdi (404), front esa bunday eslatmani ro'yxatdan olib tashlaydi:
qo'ng'iroqchada "1" turadi-yu, ro'yxat bo'sh edi.

- **§1**: eslatma endi **mahsulotga** ishora qiladi (`entity=Product`) —
  havola ishlaydi, buyurtmachi bosib mahsulot kartasida tannarx kiritadi;
  har bir narxsiz mahsulotga ALOHIDA eslatma (beshta narx — beshta ish);
  takror bosishda o'qilmagani yangilanadi (kalit user+Product);
  `price_arrived` endi o'sha mahsulotning eslatmasini yopadi;
- **§1 (ixtiyoriy qism ham qilindi)**: `GET /products/?needs_price=true`
  — ochiq konfiguratsiyada narxsiz turgan mahsulotlar (doimiy ro'yxat,
  eslatma bir martalik signal); front "Narx kutilmoqda · N" kartasi;
- **§2**: `price_arrived` `pending_clarification`ni ham uyg'otadi (narx
  kelgani holatga bog'liq emas); `request_prices` endi holat tekshiradi —
  faqat `draft`/`pending_clarification`/`pending_sales` (aks holda 400:
  narx allaqachon shartnomaga kirib bo'lgan).

---

## 8.49 10-to'plam §4: TLD endi sales'ga qaytmaydi ➡️

Eski oqimda shartnoma zanjir oxirida tuzilardi va xarid narxi mijoz
narxiga ta'sir qilardi — shuning uchun TLD avval sales'ga (mijoz
roziligiga) borardi. Yangi oqimda TLD ochilishining o'zi "hammasi
bo'lgan" degani: yechim tasdiqlangan, Didox o'tgan, boshlang'ich to'lov
kelgan; shartnomadan ochilganini esa sales'ning O'ZI ochadi — o'z
hujjatini o'zi tasdiqlashi ma'nosiz edi.

- `submit` endi har qanday TLD'ni to'g'ridan-to'g'ri bugalterga
  yuboradi (`pending_bugalter`);
- sales vazifa emas, **INFO xabar** oladi: zanjiridan pul chiqmoqda va
  muddat cho'zilishi mumkin;
- `PENDING_SALES` holati va approve/reject shoxi O'CHIRILMADI — jonli
  bazada shu bosqichda turgan hisoblar yopilmay qolmasin; faqat yangi
  hisob u yerga tushmaydi;
- front keyin `replenishmentSteps`dan "Mijoz roziligi" qadamini olib
  tashlaydi.

Testlar: sales-gate to'plami legacy rejimga o'tkazildi, seed va
zanjir testlari yangilandi. Procurement: 51/51 OK.

---

## 8.50 10-to'plam §3/§5/§6/§7: zanjir kimdaligini to'g'ri aytadi 👥

- **§3**: shartli qadam ustidan sakralmaydi — `admin_approve`
  `pending_admin`da joriy bo'ladi (SHT-00055 da admin ishni ko'rmasdi,
  SLA bugalterga yozilardi); `procurement_sent` esa "to'lov keldi,
  yetishmovchilik bor, TLD yo'q" holatda joriy (chiziq bajarib
  bo'lmaydigan "Yig'ish"ni ko'rsatib turardi). Umumiy qoida: har bir
  OPTIONAL qadamda `current_override` bor — `skipped` "bo'ladimi?"
  savoliga, override "ish shu yerdami?" savoliga javob beradi;
- **§6**: "TLD zanjiri" qadami endi qora quti emas — roli va nomi TLD
  holatidan (bugalter tekshiruvi / admin tasdig'i / to'lov kutilmoqda /
  yo'lda); SLA to'g'ri odamga yoziladi, §5 hovuz qoidasi to'g'ri
  ishlaydi (shuning uchun §6 §5 dan oldin bajarildi);
- **§5**: `/roadmaps/` qatnashish ta'rifi "surat"dan "tarix"ga o'tdi —
  `chain_actor_ids` zanjirga qo'l tekkizgan hammani mavjud maydonlardan
  yig'adi (egalar, eventlar, tasdiqlar, to'lovlar, TLD bosqichlari) va
  ular ishni yopilguncha ko'radi (bugalterning ro'yxati endi bo'sh
  emas); rol bo'yicha ko'rinish esa HOVUZ bo'ldi — o'sha roldan hali
  hech kim ishlamagan bo'lsagina (yangi zayavka hamma engineerda,
  olingach faqat oluvchisida); ildizlar prefetch bilan olinadi;
- **§7**: `Contract.delivered_by` (sales.0007) — yetkazgan buyurtmachi
  shartnomani darhol yo'qotmaydi (404 edi): ro'yxati navbat + o'zi
  yetkazganlari + o'zi TLD ochganlari; roadmap `ship` qadami ism oldi;
  pul baribir sizib chiqmaydi (qator narxlari olib tashlanadi).

---

## 8.51 11-to'plam: bitta TLD — bitta zanjir; qoldiq to'lov bugalterniki 🚪

- **§1**: "bitta ochiq TLD" qoidasi eshikni emas, ZANJIRNI qo'riqlaydi
  — `chain_open_replenishment` konfiguratsiya va shartnoma tomonlarini
  birga tekshiradi (engineer CFG'dan ochgan hisob turganda sales SHT'dan
  ikkinchisini ocha olardi: bir xil mol ikki marta buyurtma bo'lardi).
  Kuchliroq qoida ham qo'shildi: **konfiguratsiyadan tug'ilgan
  shartnomada `request-procurement` umuman yopiq** (400) — nima
  yetishmayotganini CFG biladi (`missing` o'sha yerda), shartnoma eshigi
  faqat ombordan to'g'ridan-to'g'ri sotuv uchun;
- **§2**: yetkazilgan-u qoldiq to'lanmagan shartnomada oxirgi qadam
  endi «Qoldiq to'lov» / **bugalter** (avval "Yakunlandi"/sales edi —
  bugalter ishni ko'rmasdi, SLA sales'ga yozilardi, 10-§5 hovuzi ham
  noto'g'ri rolga tayanardi). Yopilganda yana "Yakunlandi" bo'ladi.

Testlar: `apps/core/tests/test_chain_tld.py` (6).

## 8.53 12-to'plam: admin ruxsati Didoxdan OLDIN 📝

- **§1**: zanjir endi `sales → bugalter → admin → Didox → to'lov`. Admin
  tasdig'i — RUXSAT, shuning uchun ishdan (Didoxga yuborishdan) oldin
  so'raladi, hujjat hali kuchga kirmagan bosqichda. Yangi holat
  `Contract.Status.READY_FOR_DIDOX` — "tasdiqlandi, Didoxga yuborilishi
  kerak". `approve_contract` endi `didox_number` qabul qilmaydi (u faqat
  `send_didox`da); `send_didox` `ready_for_didox`dan ishlaydi;
  `confirm_didox` endi chegarani bilmaydi — natija doim `approved`.
  Eski yozuvlar (Didoxi allaqachon tasdiqlangan `pending_admin`)
  migratsiyasiz to'g'ridan `approved`ga o'tadi. Roadmapga yangi qadam —
  `bugalter_check` ("Bugalter tekshiruvi"), 18 qadam endi 19 ta.
- **§3**: engineer ishga olishdan OLDIN zayavkani qaytarsa (`returned`),
  roadmapdagi `taken` qadami endi **sales** rolida "Sales tuzatmoqda"
  deb ko'rinadi — avval qat'iy `engineer` edi, holbuki ish sales'da.
- **§4**: sales'ning yon panelida endi qaytgan zayavkalar soni ko'rinadi
  (`_request_source`, sabab `fix_and_resubmit`) — avval bu manba faqat
  engineer uchun ishlar, sales sanog'i doim 0 edi.
- **§6**: rad etilib qayta yuborilgan shartnomada chiziq ESKI
  `didox_sent_at`/`didox_accepted_at` qiymatlaridan "bajarilgan" deb
  o'ylab, joriy qadamni oldinga sakratardi. Endi bu maydonlar
  oxirgi rad etishdan KEYIN bo'lgan-bo'lmaganiga qarab tekshiriladi
  (`after_last_reject`). Admin/bugalter qadamlarining `at`/`who`si
  faqat `APPROVED` qatorlardan olinadi (rad etilgan qatordan emas).
  `contract_submitted` endi `repeats` bilan — necha marta qaytganini
  ko'rsatadi.
- **§5**: umumiy qoida hujjatga yozildi — `docs/06-WORKFLOWS.md`
  "Teskari o'tishda ikki narsa bo'lishi shart" (eslatma + navbat).

Testlar: `test_didox_and_threshold.py`, `test_didox_steps.py`,
`test_seed_demo.py` yangilandi.

## 8.52 11-to'plam §3: yetkazishni sales belgilaydi 📦

- Yetkazish "mol bilan ishlaydigan odam" qoidasiga qurilgan edi
  (buyurtmachi/bugalter) — noto'g'ri: mijoz bilan gaplashadigan, muddatni
  aytadigan va molni topshiradigan odam shartnoma egasi **sales**.
  Buyurtmachining ishi zanjirning boshqa uchida (TLD, omborga kirim).
- `ship_contract`: endi faqat **sales (shartnoma egasi) va admin**; sales
  ro'yxatida ham faqat o'z shartnomasi bor, shuning uchun egalik sharti
  amalning o'zida ham tekshiriladi.
- Ruxsat klassi `SHIP_ACTIONS` uchun `ProcurementSharedAccess`dan
  `IsAdminOrSales`ga — `ProcurementSharedAccess` o'z nomiga (ta'minot
  bo'limi) qaytdi.
- Roadmap: `('ship', 'Yetkazish', 'sales')` — qadam roli o'zgardi,
  `delivered_by` (10-§7) endi sales ismini ko'rsatadi.
- `_contract_sources`: yetkazish eslatmasi buyurtmachi shoxidan sales
  shoxiga ko'chdi (faqat `delivered_at__isnull=True`).
- Buyurtmachining shartnoma ro'yxatidan yetkazish navbati olib
  tashlandi — qolgan ikkitasi qoladi: `delivered_by=user` (eski
  yozuvlar) va `replenishments__created_by=user` (o'zi TLD ochgan
  zanjir, yopilguncha ko'rinadi).

Testlar: `test_contract_flow.py`, `test_delivered_by.py`,
`test_chain_closure.py`, `test_reservations.py` yangilandi.

## 8.54 12-to'plam §2 (C-track): bitta savdoda bir nechta model 📦

- Mijoz bir suhbatda ikki xil model so'rasa (masalan HP 880 va Dell),
  bu bitta savdo — bitta shartnoma, bitta Didox, bitta to'lov, lekin
  ikkita muhandislik ishi (har biri o'z konfiguratsiyasi).
- `ContractItem.configuration` (SET_NULL) — qator aynan qaysi modeldan
  kelganini biladi; migratsiya mavjud qatorlarni `contract.configuration`
  dan to'ldiradi (`sales.0009`).
- `POST /configurations/{id}/approve/` endi ixtiyoriy `contract` (id)
  qabul qiladi — berilsa yangi shartnoma ochilmaydi, mavjud **qoralama**
  shartnomaga yangi qator qo'shiladi (shartlar: draft, bir xil mijoz,
  bir xil egasi yoki admin).
- `Configuration.active_contract`: birinchi model `Contract.configuration`
  FK orqali, keyingi modellar `ContractItem.configuration` orqali
  topiladi — bitta joyda tuzatilgani `is_paid`, `finalize`, `_require_paid_chain`,
  `change_quantity`, `chain_open_replenishment`, roadmap `resolve_chain`,
  `cancel_chain`, procurement `receive` — hammasiga avtomatik tarqaladi.
- `finalize`ning B6 qator ko'chirishi endi `configuration=` bo'yicha
  (avval `product=base_product` edi) — ikki model bir xil bazaviy
  mahsulotdan boshlansa ham to'g'ri qatorga tegadi.
- 11-§1 "bitta ochiq TLD": endi **bir modelli** zanjirlarda shartnoma
  tomonidagi eski (konfiguratsiyasiz) TLD ham ko'rinadi (moslik saqlandi),
  lekin **ikki+ modelli** shartnomada bu traversal o'chadi — aks holda
  A modeli uchun ochilgan hisob B modelini bekorga bloklab qo'yardi.
- `archive_completed_chain`: shartnoma yopilganda **hamma** bog'langan
  modelning zayavkasi arxivlanadi, faqat birinchisiniki emas.
- **Qamrovdan tashqarida (keyingi bosqich, hujjatning o'zi shunday
  tavsiya qiladi):** B-track — bitta zayavkada bir nechta qator
  (`ConfigurationRequestLine`, sales bir zayavkada ikkita model
  so'rashi); qisman yetkazish; bitta model bekor qilinganda pul
  qaytarish — bularning barchasi ochiq savol sifatida hujjatda qoldi.

Testlar: `apps/configurator/tests/test_multi_model_contract.py` (7).

## 8.55 13-to'plam §1: shartnoma matni — bugalter yuklaydi va tahrirlaydi 📝

- Hozirgacha shartnoma matnini tizim generatsiya qilar edi (barcha
  shartnomalar uchun bir xil, `GET /contracts/{id}/print/` — bu **qoladi**,
  faqat UI dan endi bu tugma yashiriladi). Endi bugalter matnni saytning
  o'zida yozadi/tahrirlaydi yoki `.docx` yuklab boshlaydi.
- Yondashuv — hujjatning o'zi tavsiya etgan **B (boy matn, `mammoth`) +
  C (o'rin egallovchilar)**: `.docx` HTML'ga o'giriladi (formatlash
  qisman yo'qoladi, lekin matn bizning bazamizda — qidiriladi,
  versiyalanadi, avtomatik maydonlar bilan to'ladi). OnlyOffice (A)
  hujjatning o'zi aytganidek — faqat Didoxga fayl **o'sha holicha**
  ketishi kerak bo'lib chiqsa kerak bo'ladi; B dan boshlash A ga yo'lni
  yopmaydi.
- Yangi modellar: `ContractDocument` (bitta shartnomaga bitta, `body` +
  `source_file`), `ContractDocumentVersion` (har saqlash — yangi versiya,
  hujjat huquqiy).
- Yangi endpointlar: `GET`/`PUT /contracts/{id}/document/`,
  `POST /contracts/{id}/document/upload/`,
  `GET /contracts/{id}/document/versions/`.
- Tahrir qoidasi (holat bo'yicha): `draft`/`rejected`/`pending_bugalter`/
  `pending_admin`/`ready_for_didox` — ochiq; `pending_didox` dan
  boshlab (mijozga ketgan) — yopiq, faqat o'qish.
- Ruxsat: **tahrir hozircha faqat bugalterda** (admin ham yo'q — talab
  shunday), **o'qish** bugalter+admin+sales(egasi)da; engineer va
  buyurtmachiga umuman yopiq (`ContractViewSet.get_queryset` + amal
  ichidagi rol tekshiruvi — admin `RoleAccess` orqali avtomatik o'tib
  ketmasligi uchun tekshiruv qasddan servis/view darajasida, ruxsat
  klassida emas).
- O'rin egallovchilar (`{{ contract.number }}`, `{{ contract.date }}`,
  `{{ client.name }}`, `{{ client.inn }}`, `{{ items_table }}`,
  `{{ total }}`, `{{ prepayment_percent }}`, `{{ term_days }}`) —
  **ko'rsatishda** to'ladi, saqlanishda emas (summa o'zgarsa hujjat
  ham ergashadi). Narx: `{{ total }}`/`{{ prepayment_percent }}` faqat
  sales va adminga (mavjud `PRICE_FIELDS` chegarasi bilan bir xil qoida).
- `.docm` (makroli) ruxsat ro'yxatida yo'q — qo'shilmadi.
- Yangi tashqi paket: `mammoth` (+ `cobble`) — `requirements.txt`ga
  qo'shildi.
- **Qamrovdan tashqarida (hujjatning o'zi bosqichlashtirgan):**
  `.docx` eksport (7-bosqich), shablonlar/"shablondan boshlash"
  (8-bosqich), OnlyOffice integratsiyasi (agar Didoxga aynan fayl
  kerak bo'lib chiqsa).

Testlar: `apps/sales/tests/test_contract_document.py` (10).

## 8.56 QOLGAN-ISHLAR #2–#5: kichik, lekin frontni to'suvchi tuzatishlar 🔧

- **#2**: `ContractDocumentSerializer.body` — render qilingan (o'rin
  egallovchilar to'lgan) matn, muharrir shuni saqlasa ular yo'qolardi.
  Yangi `body_raw` (xom, render qilinmagan) — muharrir shuni yuklab,
  `PUT`da shuni yuboradi.
- **#3**: hujjatdagi `{{ total }}`/`{{ prepayment_percent }}` bugalterdan
  ham yashirilgan edi — bu `PRICE_FIELDS` qoidasiga (qator narxi:
  `unit_price` va h.k.) tegishli emas, shartnomaning JAMI summasi.
  Hujjat allaqachon faqat bugalter/admin/sales(egasi)ga ochiq, shuning
  uchun qo'shimcha maskalash olib tashlandi.
- **#4**: `ContractItemSerializer`ga `configuration_number` qo'shildi —
  bitta shartnomada bir nechta model bo'lsa (12-§2 C), front qatorlarni
  N ta alohida so'rovsiz ajrata oladi.
- **#5**: `test_sla.StatusChangedAtTests` beqaror edi — ikkita `save()`
  bir xil mikrosekundda bajarilsa (asosan Windows) `assertGreater`
  yiqilardi. Endi status o'zgarishidan oldin vaqt ataylab orqaga
  suriladi — test determinlashdi.

## 8.57 12-to'plam §2 (B-track): bitta zayavkada bir nechta talab 📋

- Talab: **bitta ishga ikkita zayavka ochilmasin** — mijoz ikkita model
  so'rasa, zayavka bitta bo'ladi, engineer uni bir marta ishga oladi va
  modellarni birma-bir yig'ib, birma-bir tasdiqqa yuboradi.
- Yangi model `ConfigurationRequestLine` — birinchi model
  `ConfigurationRequest.base_product`/`quantity`da qoladi (orqaga mos,
  mavjud kod/testlar o'zgarmaydi), qo'shimcha talablar shu qatorlarda.
- **Dizayn tuzatishi** (hujjatning o'zidagi xato topildi va tuzatildi):
  "har qatordan bitta konfiguratsiya" aralash buyurtmada noto'g'ri edi
  (`10 ta HP 880 + 20 ta zapas SSD` — ikkinchisi tayyor tovar, yig'iladigan
  narsa yo'q). Qator endi ikki turli: **model** (yig'iladigan —
  konfigurator orqali) va **tovar** (tayyor, konfiguratorsiz — to'g'ridan
  shartnoma qatoriga aylanadi, xuddi 8-§1 dagi "konfiguratsiyasiz
  shartnoma" mexanizmi kabi).
- `POST /configuration-requests/` — ixtiyoriy `lines[]` bilan yaratiladi.
- `take_request` — bitta amalda barcha `model` turidagi qatorlarga ham
  chernovik ochadi (`line_modes` — har biriga alohida `build`/`modify`).
  `item` turidagi qatorga konfiguratsiya kerak emas.
- `approve_configuration` (istalgan qator uchun, C-track bilan bir xil
  mexanizm) — shartnoma mavjud bo'lishi bilanoq, hali qo'shilmagan
  `item` qatorlari ham avtomatik `ContractItem` sifatida qo'shiladi.
- Zayavka endi `ConfigurationRequest.is_fully_done` orqali — barcha
  qatori (asosiy + qo'shimcha model + tovar) tugagunicha `done` bo'lmaydi.
- `release_request`/`cancel_chain` — qo'shimcha qatorlarning
  chernoviklari ham bekor qilinadi (avval faqat asosiysi).
- **Muhim tuzatish**: `Configuration`ga faqat `ConfigurationRequestLine`
  orqali ulangan (asosiy `ConfigurationRequest.configuration` FK bo'sh)
  konfiguratsiyalar sales'ning ko'rish/tasdiqlash ruxsatidan tashqarida
  qolib ketardi (`ConfigurationViewSet`/`ConfigurationItemViewSet`
  `get_queryset`, `core.services._configuration_source`,
  `roadmap._can_open`, `configurator.services._owning_request` va
  undan foydalanuvchi barcha joylar) — hammasi `extra_request_lines`
  orqali ham qidiradigan qilib tuzatildi (12-§2 C-trackdagi
  `active_contract` bilan bir xil naqsh).
- **Qamrovdan tashqarida**: qator darajasida alohida tahrirlash
  endpointi (miqdor/matn o'zgartirish `ConfigurationRequestLine`da —
  front B5 bilan birga keladi); front (B5, alohida ish).

Testlar: `apps/configurator/tests/test_request_lines.py` (7).

## 8.58 QOLGAN-ISHLAR #1/#3/#6: jonli topilgan uchta xato 🐛

- **#1 (jiddiy, jonli holat — SHT-00058)**: 12-§1 dagi orqaga moslik
  sharti ("Didoxi allaqachon tasdiqlangan bo'lsa to'g'ridan `approved`")
  12-§6 dagi qoidani hisobga olmagan edi: `didox_accepted_at` rad
  etishda TOZALANMAYDI. Natijada rad etilib qayta boshlangan shartnoma
  ESKI (endi haqiqiy emas) Didox izidan to'g'ridan `approved`ga
  sakrab, mijozdan HUJJATSIZ pul so'raladi. Yechim —
  `_didox_valid_for_current_cycle(contract)`: Didox faqat OXIRGI rad
  etishdan KEYIN tasdiqlangan bo'lsa haqiqiy hisoblanadi (roadmapdagi
  `after_last_reject` bilan bir xil mantiq, endi ikkala tomon ham shu
  qoidaga amal qiladi). **Jonli serverda `SHT-00058` shu holatda
  qolgan — qo'lda tuzatish kerak** (pastda).
- **#3**: SLA hujjatning oxirgi holat o'zgarishidan (`status_changed_at`)
  sanalardi — lekin bir nechta qadam (`procurement_sent`,
  `procurement_chain`, `assemble`, `finalize`) bitta holat (CFG
  `approved`) ichida ketma-ket bajariladi, ya'ni to'rttasi ham bitta
  vaqtdan "kechikardi". Endi har biri **o'z boshlanish vaqtidan**
  (`since=` — to'lov, TLD ochilishi, mol kelishi, yig'ilish paytidan).
- **#6**: joriy qadamda hujjat bo'lmasa (`procurement_sent` TLD hali
  yo'q paytda, `taken` konfiguratsiya hali yo'q paytda) — havola endi
  ISH BAJARILADIGAN sahifaga (mos ravishda konfiguratsiya va zayavka),
  natija hujjatiga emas (u hali yo'q, bu qoidaning o'zi).

### `SHT-00058`ni tuzatish (bir martalik) — yangi komanda

Tuzatishdan keyin ham eski yozuv o'zi to'g'irlanmaydi — statusi
allaqachon `approved`. Shu holatdagi BARCHA yozuvlarni (nafaqat
SHT-00058) topib, pul hali kelmaganlarini xavfsiz qaytaradigan
komanda qo'shildi:

```bash
make docker-fix-stale-didox           # yoki avval --dry-run bilan ko'rish:
docker compose -f docker-compose.yml -f docker-compose.caddy.yml exec web \
  python manage.py fix_stale_didox --dry-run
```

Testlar: `test_didox_steps.py` (+1), `test_roadmap.py` (+3).

---

## 9. Nima o'zgarmadi

- Auth (JWT, refresh rotatsiyasi) — o'sha-o'sha
- Shartnoma jarayoni va komissiya foizi (30% / 15%)
- Kassa yacheykalari, xarajat so'rovi (admin ruxsati)
- Kirim (UZB / Import / Ustav), import kunlari kuzatuvi
- Dashboard tuzilishi
- Sahifalash, filtr, qidiruv qoidalari
- Narxning faqat sales va adminga ko'rinishi

---

## 9.1 Serverdagi holat

Yangi versiya `ombor.thesofmebel.uz` ga chiqarilgan va ishlab turibdi.
Frontend to'g'ridan-to'g'ri shu manzil bilan ishlashi mumkin:

```
VITE_API_URL=https://ombor.thesofmebel.uz/api
```

Demo foydalanuvchilar tayyor (parol `Ombor2026!`): `admin`, `bugalter`,
`buyurtmachi`, `sales1`, `sales2` — ya'ni 4 rolning hammasi sinab ko'rilishi mumkin.

## 10. Statistika

| Ko'rsatkich | Avval | Endi |
|---|---|---|
| REST endpoint | 70 | **121** |
| Django ilovalari | 8 | **9** (`procurement` qo'shildi) |
| Modellar | 23 | **34** |
| Testlar | 66 | **462** |
| Rollar | 3 | **5** |
