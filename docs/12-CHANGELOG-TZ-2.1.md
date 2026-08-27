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
| REST endpoint | 70 | **87** |
| Django ilovalari | 8 | **9** (`procurement` qo'shildi) |
| Modellar | 23 | **28** |
| Testlar | 66 | **131** |
| Rollar | 3 | **4** |
