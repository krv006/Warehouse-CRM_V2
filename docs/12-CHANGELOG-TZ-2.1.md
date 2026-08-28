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
| REST endpoint | 70 | **92** |
| Django ilovalari | 8 | **9** (`procurement` qo'shildi) |
| Modellar | 23 | **30** |
| Testlar | 66 | **174** |
| Rollar | 3 | **5** |
