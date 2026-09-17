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
| REST endpoint | 70 | **104** |
| Django ilovalari | 8 | **9** (`procurement` qo'shildi) |
| Modellar | 23 | **33** |
| Testlar | 66 | **365** |
| Rollar | 3 | **5** |
