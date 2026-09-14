# 13 — Front uchun qolgan ishlar (buyurtmachi paneli auditi)

> 03.09.2026 da `https://warehouse-frontend-iota.vercel.app` buyurtmachi roli bilan
> jonli tekshirildi. Panelning katta qismi tayyor va backend bilan to'g'ri ulangan.
> Quyida **3 ta qolgan ish** — hammasi faqat frontdagi UI ishi, backend to'liq tayyor
> va testlangan.

## Tekshiruvda ishlagan qismlar ✅

| Bo'lim | Holat |
|---|---|
| Login, dashboard (kam qolganlar, muddati yaqin shartnoma, yo'ldagi kirimlar) | ✅ |
| Configuratordan kelgan warning'lar ("omborda yo'q butlovchilar (TLD-...)") | ✅ |
| TLD ro'yxati va kartasi (holat zanjiri, kassa, yetmayapti, qarz ranglari) | ✅ |
| Qator qo'shish modali — "Bazadan tanlash" / **"Yangi mahsulot"** tablari | ✅ |
| "Bugalterga yuborish" (submit) | ✅ |
| Low-stock sahifasi + "Hisob shakllantirish" | ✅ |
| Kirimlar (o'qish), Mijozlar + "Yangi mijoz" | ✅ |
| Rol bo'yicha menyu (kassa yo'q, configurator yozish yo'q) | ✅ |

---

## 1. "Yangi hisob" tugmasi 🔴 asosiy

**Muammo:** `/replenishments` ro'yxatida buyurtmachi **noldan alohida buyurtma ocha
olmaydi** — hozir hisob faqat low-stock sahifasidan yoki configuratordan (engineer
yuborganidan) paydo bo'ladi. TZ 7 bo'yicha buyurtmachi istalgan payt o'zi buyurtma
bera olishi kerak.

**Yechim:** ro'yxat tepasiga (qidiruv qatori yonига) **"+ Yangi hisob"** tugmasi.

### 1.1 Hisob ochish

```
POST /api/replenishments/
```

```json
{"supplier": "Etuf MCHJ", "note": "Sentyabr partiyasi"}
```

- **Hamma maydon ixtiyoriy** — bo'sh `{}` yuborsa ham chernovik ochiladi.
- `warehouse` yuborilmaydi — tizimda bitta ombor, backend o'zi oladi.
- Ruxsat: **buyurtmachi** va admin (`403` — boshqa rollarga).

**Javob** (`201`):

```json
{
  "id": 14,
  "number": "TLD-00014",
  "warehouse": 3,
  "warehouse_name": "Asosiy ombor",
  "supplier": "Etuf MCHJ",
  "configuration": null,
  "configuration_number": null,
  "status": "draft",
  "status_display": "Qoralama",
  "currency": "UZS",
  "logistics_cost": "0.00",
  "other_cost": "0.00",
  "items_total": 0,
  "total_amount": 0,
  "cash_available": "89200000.00",
  "shortfall": 0,
  "paid_amount": "0.00",
  "debt": null,
  "expected_at": null,
  "note": "Sentyabr partiyasi",
  "items": [],
  "approvals": [],
  "events": []
}
```

Javobdagi `id` bilan **mavjud TLD kartasiga** o'ting — undan keyingi hamma narsa
(Qator qo'shish, Xarajatlar, Bugalterga yuborish) allaqachon ishlab turibdi.

### 1.2 Qator qo'shish (mavjud modal, o'zgarishsiz)

Bazadagi tovar bilan:

```json
POST /api/replenishment-items/
{"replenishment": 14, "product": 9, "quantity": 10, "unit_price": "4000000"}
```

Bazada yo'q tovar bilan — **buyurtma qilishning o'zi mahsulot qo'shish** (TZ 7):

```json
POST /api/replenishment-items/
{"replenishment": 14, "product_name": "RAM 32 GB", "product_sku": "RAM-32",
 "quantity": 8, "unit_price": "900000", "supplier": "Etuf MCHJ"}
```

- `product_sku` ixtiyoriy; `product` ham, `product_name` ham bo'lmasa —
  `400 {"product": "Mahsulotni tanlang yoki yangi mahsulot nomini kiriting."}`
- Bir xil nom takrorlanmaydi — mavjud mahsulot olinadi.

### 1.3 Keyingi zanjir (mavjud, o'zgarishsiz)

```
buyurtmachi: POST /replenishments/{id}/submit/      → bugalter tekshiruvida
bugalter:    POST /replenishments/{id}/approve/     → admin tasdig'ida
admin:       POST /replenishments/{id}/approve/     → tasdiqlandi
bugalter:    POST /replenishments/{id}/pay/         → to'landi (yetmasa qarzga)
har ikkisi:  POST /replenishments/{id}/events/      → yo'lda / bojxona / keldi
             POST /replenishments/{id}/receive/     → ombor qoldig'i oshadi
             GET  /replenishments/{id}/timeline/    → line chart
```

- `submit` da narxsiz qator bo'lsa `400` + qatorlar ro'yxati keladi.
- Chernovikda tahrirlash erkin; `submit` dan keyin qatorni faqat admin o'zgartiradi.

---

## 2. TLD kartasida manba konfiguratsiya havolasi 🟡

**Muammo:** configuratordan kelgan hisobda (masalan TLD-00001) u **qaysi
konfiguratsiya uchun** ochilgani ko'rinmaydi.

**Yechim:** javobda maydonlar bor —

```json
{"configuration": 1, "configuration_number": "CFG-00001"}
```

`configuration` bo'sh bo'lmasa, karta shapkasiga havola chiqaring:
**"Manba: CFG-00001"** → `/configurations/1` sahifasiga.

Ro'yxatni konfiguratsiya bo'yicha filtrlash ham bor:
`GET /api/replenishments/?configuration=1`.

---

## 3. Ta'minotchi bo'sh qolib ketmasin 🟢 kichik

**Muammo:** chernovik hisoblarda ta'minotchi "—" bo'lib turibdi. Backend bo'sh
ta'minotchi bilan ham `submit` ni qabul qiladi, lekin hisobot va qarz uchun kerak.

**Yechim (frontda):** "Bugalterga yuborish" bosilganda `supplier` bo'sh bo'lsa —
avval to'ldirishni so'raydigan modal/ogohlantirish ko'rsating
(`PATCH /api/replenishments/{id}/ {"supplier": "..."}`).

---

## 4. Ikki xil kirim: Butlovchi / Tayyor model 🆕

Buyurtma qatori modalidagi **"Yangi mahsulot"** tabiga **tur selecti** qo'shing:

| Qiymat | Ko'rinishi |
|---|---|
| `component` | Butlovchi (default) |
| `machine` | Tayyor model |

```json
POST /api/replenishment-items/
{"replenishment": 14, "product_name": "HP 990 kompyuter",
 "product_kind": "machine", "quantity": 2, "unit_price": "18000000"}
```

Tayyor model kirim qilingach, **mahsulot kartasida** (`kind=machine`) engineer
uchun "Tarkib" bloki: qator qo'shish/tahrirlash/o'chirish —
`POST/PATCH/DELETE /api/product-specs/` (`product`, `component` yoki
`new_component_name`, `label`, `quantity`). Yozish engineer, **buyurtmachi**
va adminda (buyurtmachi tayyor modelni buyurtma qilganda tarkibini ham kiritadi);
boshqalarga tugmalar yashiriladi.

## 5. "Omborlar" sahifasi olib tashlanadi — Ombor = Mahsulotlar 🔴

**Muammo:** `/warehouses` sahifasi bitta "Asosiy ombor" yozuvini ko'rsatib turibdi —
foydasi yo'q. Biznesda **doimo bitta ombor** bo'ladi (ikkinchisini yaratish backend
darajasida bloklangan), shuning uchun "Omborlar" ro'yxati ham, "ombor qo'shish" ham
kerak emas.

**Yechim:** "Ombor" va "Mahsulotlar" **bitta sahifaga birlashadi**:

- Menyudan **"Omborlar"** (`/warehouses`) va alohida **"Qoldiqlar"** (`/stocks`)
  bandlarini olib tashlang.
- Bitta **"Ombor"** sahifasi qoladi — manba `GET /api/products/`:

| Ustun | Maydon |
|---|---|
| SKU | `sku` |
| Nomi | `name` |
| Turi | `kind_display` (Tayyor model / Butlovchi) |
| Qoldiq | `total_stock` |
| Narx | `stock_price` |
| Kam qolgan | `is_low_stock` → qizil belgi |

- Tepada tur tablari: Hammasi · Tayyor modellar (`?kind=machine`) ·
  Butlovchilar (`?kind=component`).
- Mahsulot kartasi (`GET /products/{id}/`) — `specs[]` tarkibi bilan
  (engineer'ga "Tarkib" tahriri, §4).
- "Harakatlar tarixi" (`/movements`) alohida sahifa bo'lib qolishi mumkin.
- Hech qayerda `warehouse` select/ustun ko'rsatilmaydi.

Backend'da o'zgarish shart emas — `GET /products/` da hamma kerakli maydon bor.

## 6. Mahsulot selecti — qidiruvli autocomplete 🟡

**Muammo:** configurator qatorini tahrirlashda (`/configurations/{id}`) butlovchi
selecti **barcha mahsulotlarni** ro'yxat qilib chiqaryapti. Katalog o'sgan sari bu
ishlatib bo'lmaydigan bo'lib qoladi — "SSD" deb yozganda faqat mos nomlilar
chiqishi kerak.

**Yechim:** oddiy `<select>` o'rniga **qidiruvli autocomplete** (combobox).
Backend tayyor — nom va SKU bo'yicha qidiradi:

```
GET /api/products/?search=ssd
```

Jonli serverda tekshirilgan javob (faqat moslari keladi):

```
MAH-00025 — 5TB SSD
1234      — SSD 1 TB
SSD-1TB   — SSD disk 1 TB
```

Tavsiya qilingan ishlash tartibi:

- foydalanuvchi yozishni boshlaganda (2+ belgi) `?search=<matn>` so'raladi,
  300 ms debounce bilan;
- variant ko'rinishi: `sku — name` (hozirgidek), yonida `total_stock` ko'rsatilsa
  yanada yaxshi ("omborda: 5");
- konfigurator qatori uchun `&kind=component` qo'shib faqat **butlovchilarni**
  chiqaring (tayyor modellar butlovchi bo'lolmaydi);
- bo'sh qidiruvda birinchi sahifa (20 ta) ko'rsatiladi — `?page=` bilan davomi.

Xuddi shu autocomplete boshqa joylarda ham ishlatilsin:

| Joy | So'rov |
|---|---|
| Configurator qatori (butlovchi) | `/products/?search=...&kind=component` |
| To'ldirish qatori ("Bazadan tanlash") | `/products/?search=...` |
| Tarkib (product-specs) qatori | `/products/?search=...&kind=component` |
| Zayavkada bazaviy model | `/products/?search=...&kind=machine` |

Backend'da o'zgarish shart emas — `search`, `kind` filtri va sahifalash bor.

## 7. Kelishuvlar — tahrirlash va aloqa eslatmasi 🟡

**Muammo:** `/leads` sahifasida faqat "Yangi kelishuv" bor — yaratilgan
kelishuvni **tahrirlab bo'lmaydi** (bosqichni o'zgartirish, keyingi aloqa
sanasini surish, shartnomaga bog'lash).

**Yechim (backend tayyor, endpoint bor):**

- Qatorda "Tahrirlash" — o'sha modal oldindan to'ldirilgan holda ochiladi,
  saqlash: `PATCH /api/leads/{id}/` (istalgan maydon: `stage`, `title`,
  `expected_amount`, `next_contact_at`, `note`, `client`, `contract`).
- Bosqich "Shartnoma tuzildi" tanlanganda `contract` ni ham so'rang —
  shunda jadvaldagi SHARTNOMA ustunida havola chiqadi.
- O'chirish kerak bo'lsa: `DELETE /api/leads/{id}/`.

**Aloqa eslatmasi (yangi, backend qildi):** "Keyingi aloqa" sanasi kiritilgan
bo'lsa, sana kelganda kelishuvni yaratgan sales'ga notification tushadi —
bugun/ertaga sariq, o'tib ketgan qizil ("Aloqa N kun oldin bo'lishi kerak edi").
Sana kiritilmagan bo'lsa eslatma bo'lmaydi.

- Notification ro'yxatida `entity='Lead'` kelganda `/leads` dagi o'sha qatorga
  havola qiling (`object_id` — lead id).
- Jadvalda KEYINGI ALOQA sanasi o'tib ketgan bo'lsa qizil rangda ko'rsatilsin.

## 8. Bajaruvchi rekvizitlari — sozlamalar sahifasi 🟡

Shartnoma chop etish shaklidagi **BAJARUVCHI** bloki (firma nomi, STIR, tel,
email, manzil, bank, MFO, hisob raqam, rahbar) endi backendda saqlanadi —
yagona yozuv:

```
GET  /api/company/          — hamma o'qiydi (chop etishda ishlatiladi)
PUT  /api/company/          — faqat admin to'ldiradi/tahrirlaydi (PATCH ham bor)
```

Front vazifasi:

- **Sozlamalar** bo'limida "Kompaniya rekvizitlari" sahifasi — faqat admin
  menyusida; forma maydonlari: `name`, `inn` (STIR), `phone`, `email`,
  `address`, `bank_name`, `mfo`, `account_number`, `director_name`,
  `contract_terms` (textarea — shartnoma pastidagi standart shartlar).
- Birinchi GET bo'sh qiymatlar qaytaradi (`""`) — "hali to'ldirilmagan"
  holatini ko'rsating.
- **Shartnoma chop etish modalida** BAJARUVCHI blokini shu endpointdan
  to'ldiring (hozir front o'zida qattiq yozilgan/noto'g'ri maydon ishlatyapti —
  rasmda BUYURTMACHI nomi o'rniga shifrlangan satr chiqqan, mijoz nomini
  `client.display_name` dan oling).
- Admin bo'lmagan foydalanuvchi formani ko'rsa ham saqlay olmaydi (403) —
  tugmani yashiring.

## 9. QQS (NDS) — hisob-faktura ko'rinishi (buyurtmachi + sales) 🔴 MUHIM

Backend har ikkala oqimda QQS'ni to'liq hisoblab beradi. Front vazifasi —
rasmdagi jadval ko'rinishini ikki joyda ko'rsatish:

**A. Buyurtmachi — to'ldirish hisobi (TLD).** Buyurtmachi mahsulotlarni kiritib
bo'lgach, **submit'dan oldin** hisob-faktura modali ochiladi: barcha qatorlar,
har qatorda tahrirlanadigan **QQS %** input (`PATCH /api/replenishment-items/{id}/`
`{"vat_percent": "12"}`), pastda yig'indilar. Tasdiqlagach `submit` — hujjat
bugalterga boradi va **bugalter xuddi shu modalni ko'rib** approve/reject qiladi.

**B. Sales — shartnoma.** Shartnoma qatorlarini kiritganda xuddi shu jadval:
har qatorda QQS % (default 12 — backend o'zi qo'yadi, sales o'zgartira oladi,
masalan imtiyozli mahsulotga 0), pastda uch yig'indi. Chop etish modali (8-bo'lim)
ham shu qiymatlardan chiziladi.

**Jadval ustunlari → API maydonlari:**

| Ustun | Shartnoma (`/contracts/` items) | To'ldirish (`/replenishment-items/`) |
|---|---|---|
| Tovar nomi | `product_name` | `product_display` |
| Birlik | "dona" (statik) | "dona" (statik) |
| Soni | `quantity` | `quantity` |
| Narx (QQS'siz) | `unit_price` | `unit_price` |
| QQS % | `vat_percent` — **default 12** | `vat_percent` — **default 0**, buyurtmachi kiritadi |
| QQS (summa) | `vat_amount` (o'qish) | `vat_amount` (o'qish) |
| Jami | `total_with_vat` (o'qish) | `total_with_vat` (o'qish) |

Seriya / Shtrix ustunlari hozircha backendda yo'q — "—" ko'rsating.

**Pastki yig'indi qatori** (ikkala hujjat javobida tayyor keladi):

```
Yetkazish: items_total · QQS: vat_total          Jami: items_total_with_vat
```

TLD'da bundan tashqari: `total_amount` = `items_total_with_vat` + `logistics_cost`
+ `other_cost` — bugalter `pay` bosqichida kassadan shu summa ketadi.

**Muhim o'zgarishlar (breaking emas, lekin bilish shart):**

- Shartnomada `total_amount` endi **QQS bilan** sinxronlanadi (summa qo'lda
  yuborilmaganda). Oldindan to'lov (30%/15%) va balans ham shu summadan.
- Bugalter shartnoma javobida qator narxlarini ko'rmaydi — endi `vat_percent`,
  `vat_amount`, `total_with_vat` ham yashirin (faqat sales/admin ko'radi);
  umumiy `total_amount`, `items_total`, `vat_total` esa ko'rinadi.
- To'ldirishda QQS default 0 — ta'minotchi hisobida QQS bo'lsa buyurtmachi
  foizni o'zi kiritadi; eskicha ishlayotgan frontga hech narsa buzilmaydi.

## 10. Sales-gate — TLD'da mijoz roziligi bosqichi 🔴 MUHIM

Mijoz buyurtmasidan (konfiguratsiyadan) ochilgan to'ldirish hisobi endi
buyurtmachi `submit` qilganda **bugalterga emas, avval sales'ga** boradi —
yangi status: `pending_sales` ("Sales — mijoz roziligi kutilmoqda").

Oqim:

```
buyurtmachi narx+QQS kiritadi → submit
  ├─ configuration bor  → pending_sales → sales approve → pending_bugalter → admin → pay
  └─ configuration yo'q → pending_bugalter → admin → pay (eskicha)
```

Front vazifasi:

- **Sales menyusida** "To'ldirish hisoblari" ko'rinishi kerak (sales endi
  `GET /api/replenishments/` ni o'qiy oladi) — kamida `?status=pending_sales`
  filtrli ro'yxat: "Mijoz roziligi kutilayotganlar".
- Sales hisobni ochganda 9-bo'limdagi **hisob-faktura ko'rinishi** (QQS bilan)
  chiqadi + ikkita tugma: **"Mijoz rozi — tasdiqlash"**
  (`POST /api/replenishments/{id}/approve/` `{"comment": "..."}`) va
  **"Rad etish"** (`POST .../reject/`) — rad etilsa hisob buyurtmachiga
  qaytadi (`rejected`, tahrirlab qayta yuborsa bo'ladi).
- Submit'da sales'larga notification tushadi (`entity='Replenishment'`,
  sarlavhasi "mijoz roziligi kerak") — bosilganda shu hisobga olib boring.
- Status badge'lariga `pending_sales` qo'shing; `approvals[]` tarixida yangi
  `step: "sales"` ("Sales — mijoz roziligi") chiqadi.
- Bugalter oynasida hech narsa o'zgarmaydi — unga hisob faqat sales
  tasdig'idan keyin tushadi (oddiy to'ldirish esa eskicha to'g'ri tushadi).

Maqsad: bugalter va adminga faqat mijoz "ha" degan hisoblar borsin —
ular bo'sh ish bilan band bo'lmasin.

## Eslatma: oxirgi backend o'zgarishlari (allaqachon serverda)

| Nima | Frontga ta'siri |
|---|---|
| Login throttle | 429 kelsa: "Urinishlar ko'payib ketdi, bir daqiqadan keyin urining" |
| Fayl yuklash cheklovi | 400 dagi `file` xabarini ko'rsating; inputga `accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx"` |
| Bitta ombor | hech qayerda `warehouse` yuborish shart emas, ombor selectlari olib tashlanadi |

To'liq o'zgarishlar tarixi: [12-CHANGELOG-TZ-2.1.md](12-CHANGELOG-TZ-2.1.md).
