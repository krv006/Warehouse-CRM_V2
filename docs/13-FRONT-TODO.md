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

## 11. Shartnoma avtomatik ochiladi + chop etish shakli backenddan 🔴 MUHIM

**A. Finalize'dan keyin shartnoma tayyor.** Sales konfiguratsiyani ACT bilan
yakunlaganda (`POST /configurations/{id}/finalize/`) backend o'zi **draft
shartnoma** ochadi — javobda keladi:

```json
{"...": "konfiguratsiya maydonlari",
 "contract": {"id": 7, "number": "SHT-00007", "status": "draft"}}
```

- Finalize muvaffaqiyatli bo'lgach sales'ni **shu shartnoma sahifasiga**
  olib o'ting — u tekshiradi, kerak bo'lsa tahrirlaydi, so'ng `submit`.
- Mijoz qayerdan: finalize tanasida `{"client": id}` yuborsangiz o'sha;
  yubormasangiz zayavkadagi (ZVK) mijoz. Ikkalasi ham yo'q bo'lsa
  `contract: null` — "shartnomani qo'lda oching" deb ko'rsating.
  **Tavsiya:** zayavka (ZVK) formasida mijoz select'i bor (`client` maydoni,
  backendda allaqachon mavjud) — shuni majburiy qilib to'ldiring, shunda
  zanjir oxirigacha avtomatik bog'lanadi.

**B. Chop etish modali — endi hamma ma'lumot bitta endpointdan:**

```
GET /api/contracts/{id}/print/     (faqat sales/admin)
```

Rasmdagi modal maydonlari:

| Modal qismi | Javob maydoni |
|---|---|
| BAJARUVCHI bloki | `company{name, inn, phone, email, address, ...}` |
| BUYURTMACHI bloki | `client{name, inn, phone, email, address, ...}` — `name` tayyor `display_name` (hozirgi shifrlangan satr xatosi shu bilan tuzatiladi) |
| Jadval qatorlari | `items[]`: `name`, `unit` ("dona"), `quantity`, `unit_price`, `vat_percent`, `vat_amount`, `total_with_vat`; Seriya/Shtrix — "—" |
| Pastki yig'indi | `totals`: `items_total` (Yetkazish), `vat_total` (QQS), `total` (Jami) |
| Sana qatori | `signed_at` — `deadline` (start_date + term_days; pul tushmagan bo'lsa null) |
| Shartlar matni | `terms` (admin `/company/` da kiritgan standart matn) + `note` |
| Imzo qatori | `company.name` / `client.name` |

"Chop etish / PDF" — brauzer print oynasi bilan (backend PDF bermaydi,
kerak emas). Bugalterga bu endpoint 403 — tugmani unga ko'rsatmang.

## 12. Konfiguratsiyada "Buyurtmachiga yuborilgan" flagi 🔴 MUHIM

**Muammo (siz topgan):** yetishmayotganlar buyurtmachiga yuborilgach
konfiguratsiya sahifasida buni aniqlab bo'lmasdi. Endi backend flag beradi.

`GET /configurations/` va `GET /configurations/{id}/` javobida:

```json
{
  "sent_to_procurement": true,
  "procurement": {
    "id": 4, "number": "TLD-00004",
    "status": "pending_sales",
    "status_display": "Sales — mijoz roziligi kutilmoqda",
    "is_open": true, "created_at": "..."
  }
}
```

**Nima qilish kerak:**

1. **Badge:** `sent_to_procurement === true` bo'lsa konfiguratsiya sarlavhasi
   yonida badge: `🚚 Buyurtmachida — TLD-00004 (Sales — mijoz roziligi
   kutilmoqda)`. Matn tayyor: `procurement.number` + `procurement.status_display`.
   Badge'ni bosganda TLD sahifasiga o'tkazing (`/replenishments/{procurement.id}`).
2. **Tugma:** `sent_to_procurement === true` bo'lsa "Buyurtmachiga yuborish"
   tugmasini **yashiring yoki disable qiling** — backend baribir 400 beradi:
   `{"detail": "... allaqachon ochilgan ...", "replenishment": 4}`.
3. **Tarix:** `procurement !== null` lekin `is_open === false` — oxirgi hisob
   bekor qilingan yoki omborga kirim bo'lgan; xohlasangiz kulrang badge bilan
   "TLD-00004 — Bekor qilingan" deb ko'rsating, tugma yana faol bo'ladi.
4. **Statuslar lug'ati** (badge rangi uchun): `draft`/`rejected` — buyurtmachida
   (sariq), `pending_sales` — sizda/salesda (ko'k), `pending_bugalter`/
   `pending_admin` — tasdiqda, `approved`/`ordered`/`in_transit`/`customs` —
   yo'lda, `delivered` — kelib bo'lgan (yopiq), `cancelled` — bekor (yopiq).
   Aniq matnni har doim `status_display`dan oling.

Ro'yxat sahifasida ham xuddi shu maydonlar bor — kartochkalarga kichik
badge chiqarsangiz engineer nimalar buyurtmachida turganini bir qarashda ko'radi.

## 13. AUDIT bosqichi — §10 tuzatishlari va §11 o'zgarishlari 🔴 KATTA

Backend BIZNES-LOGIKA auditi bo'yicha to'liq yangilandi. Front uchun bo'lim-
bo'lim:

### 13.1. §11.1 — ACT va Yakunlash endi ENGINEERDA

- `permissions.ts`: SALES'dan `acts.view/manage`, `configurations.finalize`
  olinadi; ENGINEER'ga qo'shiladi. Menyu bandi ruxsat bilan o'zi ko'chadi.
- `finalize-dialog` engineer sahifasiga ko'chadi; `complete` + `finalize` ni
  **bitta tugma** qiling: "Yakunlash va salesga topshirish".
- `sales-queue` 2-qadam olib tashlanadi; `engineer-queue`ga qo'shiladi.
- Finalize javobida yangi: `assembled` (yig'ildimi) va `assembly_missing[]`
  (qaysi butlovchi kutilmoqda). `assembled=false` bo'lsa konfiguratsiyada
  "Yig'ish" tugmasi: `POST /configurations/{id}/assemble/` (butlovchi yetmasa
  400 nomlar bilan — narxsiz).

### 13.2. §11.2 — Didox bo'linishi

- `pending_bugalter` tasdiq oynasi: `didox_number` maydoni + "Didoxdan qabul
  qilib, tanishib chiqdim" matni. Tana: `{"didox_number": "...", "comment": "..."}`.
- `CONTRACT_STEPS`: `Bugalter` → "Bugalter — Didox", `To'lov kutilmoqda` →
  "Bugalter — to'lov". Tasdiq tarixida yangi `payment` qadami keladi
  (`step_display` tayyor).
- Shartnomada yangi maydonlar: `didox_number`, `didox_accepted_at`;
  chop etish javobida ham `didox_number` bor.

### 13.3. §11.3 — Admin chegarasi

- Sozlamalar → Rekvizitlar: `admin_approval_threshold` maydoni (0 — chegara
  yo'q). Yozib qo'ying: taqqoslash **QQS bilan** va faqat **UZS**.
- Kichik shartnomada bugalter tasdig'idan keyin status to'g'ridan-to'g'ri
  `approved` keladi — bosqich chizig'i shunga tayyor bo'lsin; tarixda
  `decided_by=null` bo'lgan avtomatik admin yozuvi bor ("Chegara ... past").

### 13.4. §11.4 — BRON

- Mahsulot javobida: `total_stock` · `reserved_hard` (Band) · `reserved_soft`
  (Rejada) · `sellable_stock` (Erkin) · `plannable_stock` (Rejadan keyin).
  Ombor jadvalida qoldiq ustunini shu 4 ga bo'ling.
- Konfiguratsiya qatorida `available` endi **rejadan keyingi** xavfsiz raqam;
  xom qoldiq — `stock_total`. Izoh chiqaring: "omborda 5 · sizga xavfsiz 1".
- Yangi sahifa/bo'lim: `GET /reservations/` (filtr: product, kind, status);
  mahsulot kartasida "Bron" bo'limi. Qo'lda bo'shatish — faqat admin:
  `POST /reservations/{id}/release/` `{"note": "sabab"}` (majburiy).
- Sozlamalar → Rekvizitlar: `contract_reservation_days` (7),
  `configuration_reservation_days` (14) maydonlari.
- Muddati o'tganda egasiga bildirishnoma tushadi — qo'ng'iroqcha ko'rsatadi.

### 13.5. Mayda, lekin muhim

- **Katalog PATCH ochildi** (§10.2): mahsulot kartasida admin/bugalter uchun
  `sale_price`, `cost_price`, `reorder_level`, `is_active` tahriri.
  "Minimal daraja" ustunini qaytarsangiz bo'ladi — endi tahrirlanadi.
- **Shartnoma qulfi** (§10.3): `draft`/`rejected` dan keyin qator tahririni
  yashiring — backend 403 beradi (admin istisno). `rejected` shartnoma endi
  tahrirlanadi va qayta `submit` bo'ladi. Qator o'zgarganda `total_amount`
  backendda o'zi yangilanadi — `syncContractTotal()` kerak emas.
- **KIR**: status faqat oldinga (`received`/`cancelled` — terminal, backend
  400); TLD `receive`da avto-KIR ochiladi — TLD javobidagi `purchase`
  maydonidan havola qiling, bugalterga "hujjat biriktiring" xabari boradi.
  Bunday KIRda "Qabul qilish" tugmasi bo'lmasin (400: TLD orqali kelgan).
- **Kassa sizmasin** (§10.4): TLD javobida `cash_available`/`shortfall`
  admin/bugalterdan boshqaga `null`; `/dashboard/` `kassa` bloki ham `null` —
  null-check qo'ying.
- **Tranzaksiya → hujjat** (§10.9): endi `replenishment` FK va
  `replenishment_number` keladi — `documentLink()` matn parsing o'rniga
  shundan foydalansin.
- **Zanjir yopilishi** (§10.8): CFG `sold`, ZVK `archived` — navbat
  so'rovlarini soddalashtiring (`useConfigurationsWithoutContract` kerak
  emas: `ready` = shartnomasiz, `sold` = yopilgan); Lead avtomatik
  `contract` bosqichiga o'tadi — kanban shunga tayyor bo'lsin.
- `attach` endpointi va `attached` holati o'chirildi (§10.7).

## 14. Bildirishnoma manzillari (EGALIK A-to'plam) 🟢 front ishi minimal

Backend endi xabarlarni aniq egasiga yo'naltiradi: sales faqat O'Z zayavkasi
bo'yicha xabar oladi, muddat eslatmalari rolga qarab boradi, `user=null`
umumiy xabar yo'q. Frontda o'zgarish shart emas — qo'ng'iroqcha avvalgidek
`/notifications/` ni o'qiyveradi (endi shovqin keskin kamayadi).
TLD javobiga keyingi bosqichda `owner_sales` filtri qo'shiladi (B-to'plam).

## 15. Navbat + yon panel hisoblagichi + "Xodim" (EGALIK B-to'plam) 🔴

### 15.1. Yon panel badge'lari

- `GET /api/sidebar-counts/` — 60 soniyada bir (`refetchInterval: 60_000`,
  `refetchIntervalInBackground: false`, `staleTime: 15_000`,
  `refetchOnWindowFocus: true`, `enabled: Boolean(user)`).
- Global invalidatsiya BITTA joyda — `MutationCache.onSuccess` da
  `invalidateQueries(['sidebar-counts'])` (har mutatsiyaga qo'lda yozilmaydi).
- `NavItem` ga `count?: keyof SidebarCounts` maydoni; 0 — badge yo'q;
  akkordeon yopiq bo'lsa guruhda yig'indi; yig'ilgan panelda nuqta;
  `99+`; rang `primary`; xato jim yutiladi — menyu ishlayveradi.

### 15.2. Bosh sahifa navbati — endi bitta so'rov

`GET /api/my-work/` — eski 3-6 talik so'rov to'plamini almashtiradi.
Havola: `entityLink(item.entity, item.id)`. Matn: `reason` kodi bo'yicha
frontda lug'at (kodlar ro'yxati 05-API da). `level=danger` birinchi.
Raqamlar yon panel bilan ta'rifan bir xil — ikkala manba bitta funksiya.

### 15.3. "Xodim" ustuni va filtri (admin/bugalter)

- `created_by_name` endi shartnoma va konfiguratsiyada (to'liq ism).
- Filtr: `?created_by=3` (shartnoma/konfiguratsiya/zayavka/TLD),
  TLD da `?owner_sales=3` ham. Tanlov `GET /users/?role=sales` dan —
  bugalterga ham ochildi. Qiymat URL da saqlansin.
- Ustun faqat hammasini ko'radigan rollarda (admin, bugalter, buyurtmachi).
- Zayavkada ikkala xodim: `created_by_name` (kim so'radi) va
  `taken_by_name` (kim bajaryapti).

### 15.4. Bosqichda egasining ismi (§6)

Birinchi qadam "Chernovik" o'rniga **tuzgan sales ismi**
(`created_by_name`); qolgan qadamlar o'zgarishsiz. O'z hujjatida "Siz" deb
yozish mumkin. Uzun ism: `max-w-[10ch]` + `truncate` + `title`.
⚠️ Admin foydalanuvchilarning ism-familiyasini to'ldirsin — aks holda
`sales1` chiqadi.

## 16. Hujjat egaligi (EGALIK C-to'plam) 🔴

Backend endi obyekt darajasida filtrlaydi — front ro'yxatni qo'shimcha
filtrlamaydi, u o'zi qisqargan bo'lib keladi. Ikki joy o'zgaradi:

1. **Tugmalar:** "Tahrirlash"/"Yuborish" boshqaning hujjatida chiqmasin —
   `created_by` javobda bor, joriy user id bilan solishtiring (admin doim
   ko'radi). Endi boshqaniki baribir **404** (403 emas — hujjat borligi ham
   bilinmasin).
2. **Bo'sh ro'yxat matni:** "Shartnoma yo'q" emas — **"Sizda shartnoma
   yo'q"** (sales tizimda umuman shartnoma yo'q deb o'ylamasin). Kelishuv,
   zayavka, konfiguratsiyada ham shunday.

Diqqat: sales endi TLD ro'yxatida O'Z hisobini butun yo'l davomida ko'radi
(`canOpenReplenishment` da sales qatori `true` bo'ladi); boshqa sales'niki
va egasiz qoralamalar 404 — sales'ning TLD sahifasi shunga
moslansin. Buyurtmachi TLD kartasidagi konfiguratsiya havolasi buyurtmachiga
404 beradi (konfiguratsiya unga ochiq emas) — havolani faqat ko'ra oladigan
rollarga chizing. `reassign` (egasini almashtirish) hozircha yo'q — ta'tilda
admin davom ettiradi.

## 17. TLD admin chegarasi (TOPSHIRIQ #2) 🟠

- Sozlamalar → Rekvizitlar: yangi `replenishment_approval_threshold` maydoni
  (shartnomadagi `admin_approval_threshold` yonida). Izoh: QQS+xarajatlar
  bilan, faqat UZS, 0 — chegara yo'q.
- `replenishmentSteps()` dinamik bo'lsin: bugalter tasdig'idan keyin status
  to'g'ridan-to'g'ri `approved` kelishi mumkin — "Admin" qadami chizilmaydi
  (tarixda `decided_by=null` avtomatik yozuv bor, undan bilsa bo'ladi) —
  `src/modules/replenishments/lib/transitions.ts`.

## 18. SLA — turib qolgan ish qizil (TOPSHIRIQ #3) 🔴

Deyarli tayyor: `danger` allaqachon qizil chiziladi va birinchi turadi.
Qo'shiladigani:

- `work-reason.ts` ga `stale` matni ("Muddatidan ortiq turibdi").
- Qatorda `holder_name` + `waiting_days` ko'rsatish: "Bugalterda 2 ish kuni".
- O'z qatorida `waiting_days` kelsa ham ko'rsatish ("2 ish kundan beri sizda").
- Sozlamalar → Rekvizitlar: `sla_cutoff_hour` va `sla_working_days`
  maydonlari (izoh bilan: kesim soatidan keyin kelgan ish keyingi ish
  kunidan sanaladi; dam olish kunlari sanalmaydi).

## 19. Qarz/kassa tuzatildi (TOPSHIRIQ-2 #1) 🟢 front ishi yo'q

Raqamlar to'g'rilanadi, ko'rinish o'sha-o'sha. Deploy'dan keyin kassa
qoldig'i KAMAYADI (fantom pul yo'qoladi) — bu kutilgan natija, xato emas;
migratsiya logida qancha kamaygani yozib qo'yiladi.

## 20. Konfiguratsiya tasdiq zanjiri (TOPSHIRIQ-2 #4) 🔴 KATTA

- Konfiguratsiya kartasiga **bosqichlar chizig'i** (shartnomadagi kabi):
  Chernovik → Sales ko'rigi → Tasdiqlandi → Yig'ildi → Tayyor. Tarix —
  `approvals[]` (izohlari bilan).
- Tugmalar: engineer'da **"Salesga yuborish"** (`submit`), keyin alohida
  **"Yig'ish"** (`assemble`, modify'da `removals` shu yerda) va
  **"Yakunlash"** (`finalize`) — eski "Yakunlash va salesga topshirish"
  bitta tugmasi YO'Q. Sales'da `approve` / `reject` (izoh maydoni bilan).
- `assemble` javobidagi `act_suggestion` — ACT formasiga tayyor matn
  sifatida qo'yib bering (engineer tahrirlaydi).
- Navbatlar: sales'ga `configuration_review` ("Konfiguratsiyani ko'rib
  chiqing"), engineer'ga `assemble` ("Mol keldi — yig'ing") va
  `finalize_ready` sabablari uchun matnlar (`work-reason.ts`).
- `request-procurement` endi faqat `approved`da ishlaydi — tugmani shu
  holatda ko'rsating; `complete` endpointi o'chirildi.

## 21. Partiya — Miqdor maydoni (TOPSHIRIQ-2 #3) 🔴

- Zayavka va konfiguratsiya formalariga **"Miqdor"** maydoni (`quantity`).
- Konfiguratsiya sarlavhasida `HP 880 × 100`; tarkib jadvalida izoh:
  `kerak: 1 × 100 = 100` (backend `total_needed`/`shortage`ni allaqachon
  ko'paytirib beradi — front faqat ko'rsatadi).
- Yetishmovchilik/`assembly_missing` avvalgidek ishlaydi — raqamlar endi
  partiya bo'yicha.

## 22. Yetkazish (`ship`) va shartnomadan ta'minot (TOPSHIRIQ-2 #2) 🔴

- Shartnoma kartasida **"Yetkazish"** tugmasi: `active` + mol to'liq band
  bo'lganda faol (`POST /contracts/{id}/ship/` — buyurtmachi/bugalter;
  sales'ga chizilmasin). Bosqichlar chizig'iga **"Yetkazildi"** qadami
  (`delivered_at`).
- To'lovdan keyin shartnoma endi `completed` bo'lmaydi — balans nol
  bo'lsa ham yetkazilmaguncha `active`; yopilish `ship`da.
- Yetishmovchilik ogohlantirishi yoniga **"Buyurtmachiga yuborish"**
  tugmasi (`POST /contracts/{id}/request-procurement/`, sales) —
  konfiguratsiya kartasidagi bilan bir xil; TLD javobida `contract`/
  `contract_number` keladi, `?contract=` filtri bor.
- Buyurtmachi navbatida yangi qator: `ship_contract` ("Yetkazing")
  — matni `work-reason.ts`ga; buyurtmachi endi faol-yetkazilmagan
  shartnomalarni ochib ko'ra oladi (narxlar unga baribir ko'rinmaydi).

## 23. "Yig'ish" / "Buyurtmachiga yuborish" — bitta qoida (3-to'plam §1–2) 🔴

Konfiguratsiya javobida yangi `missing` ro'yxati bor — ombordan olinishi
kerak-u, yetishmayotgan pozitsiyalar. `modify` da **bazaviy model ham shu
yerda** (`kind: "machine"`), mashina ichidagi o'zgarmagan qismlar esa yo'q:

```json
"missing": [
  {"product": 12, "name": "Dell OptiPlex 7010 MT", "kind": "machine",
   "needed": 10, "available": 2, "shortage": 8}
],
"missing_count": 1
```

Qoida bitta qator (holat `approved` bo'lganda):

- `missing.length === 0` -> **"Yig'ish"** tugmasi (`POST .../assemble/`);
- `missing.length > 0` -> **"Buyurtmachiga yuborish · {missing.length}"**
  (`POST .../request-procurement/`) — "Yig'ish" umuman ko'rsatilmaydi,
  u baribir 400 beradi. Alohida ogohlantirish bloki ham shart emas.

Diqqat: tarkib jadvalidagi qator darajasidagi "Omborda"/"Yetishmaydi"
ustunlari `modify` da yetishmovchilik manbai EMAS — u yerda mashina
ichidagi qismlar ham turadi. Yetishmovchilik faqat `missing` dan o'qilsin.

`available` endi manfiy kelmaydi (§3): manfiy o'rniga `0` + alohida
`overbooked` maydoni (tarkib qatorlarida ham, `missing` da ham).
`overbooked > 0` bo'lsa "omborda 0, ustiga N dona ortiqcha va'da
qilingan" deb yozing — `shortage` bu teshikni ham yopib buyurtma qiladi.

---

## 24. Partiyani o'zgartirish tugmasi (4-to'plam §2) 🔴

Yangi endpoint: `POST /configurations/{id}/change-quantity/` —
`{"quantity": 100, "comment": "..."}` (izohni majburiy qiling).

- Konfiguratsiya kartasida sarlavha yonidagi partiya (`HP 880 × 100`)
  bosiladigan bo'lsin yoki kichik "Miqdorni o'zgartirish" tugmasi —
  oyna: yangi son + izoh;
- Tugma faqat `draft` / `pending_sales` / `approved` da va
  `assembled_at` bo'sh bo'lganda ko'rinsin; ochiq TLD chernovikdan
  o'tgan bo'lsa backend 400 beradi (xabarida TLD raqami bor — shuni
  ko'rsating);
- Muvaffaqiyatda: `approved` bo'lgan hujjat `pending_sales` ga qaytadi
  — sales navbatiga `configuration_review` qatori o'zi tushadi,
  qo'shimcha front ishi yo'q; javob — yangilangan konfiguratsiya.

---

## 25. "Hammasini o'qildi qilish" (4-to'plam §4) 🟠

- `POST /notifications/mark-all-read/` — javob `{"updated": N}`;
  tugmani eslatmalar sahifasida va qo'ng'iroqcha ostidagi ro'yxatda
  ko'rsating (faqat o'qilmagani bo'lsa);
- Ish bitganda eslatma endi backendda o'zi yopiladi (tasdiq/to'lov/
  yetkazish/yig'ish amallarida) — qo'ng'iroqchadagi son haqiqiy
  ma'noga ega bo'ldi, qo'shimcha front ishi yo'q;
- `/notifications/?entity=Contract&object_id=36` — endi ishlaydi:
  hujjat sahifasida "shu hujjat bo'yicha xabarlar" bo'limini chizish
  mumkin (ixtiyoriy).

---

## 26. YANGI OQIM — shartnoma zanjir boshida (bosqichma-bosqich) 🔴🔴

Katta o'zgarish keldi: zanjir endi `CFG → SHT → pul → mol`. Front ishlari
(F1–F11) **backend 5-bosqichi (roadmap B8) tugagach** boshlanadi — hozircha
bilib turish uchun:

- `approve` javobida va konfiguratsiya detalida `contract` maydoni bor:
  `{id, number, status, total_amount, prepayment_amount, paid, is_paid}`;
- `submit` narxsiz qatorda 400; yangi `request-prices` endpointi;
- buyurtmachi mahsulot kartasida narx kirita oladi (PATCH /products/{id}/);
- ta'minot/yig'ish endi to'lovdan keyin (B4): `configuration.contract.is_paid`
  false bo'lsa engineer tugmalari o'rniga "SHT-… · to'lov kutilmoqda" qatori;
- bekor qilish (B12/F9): uchala detalda "Zanjirni bekor qilish" tugmasi —
  `POST …/cancel/ {"reason": "..."}` (sabab majburiy); javobdagi `warnings`
  toast bo'lib chiqadi; to'lov bo'lgan shartnomada tugma chizilmaydi;
- zayavka ekrani (B15/F11): `new`/`in_progress` da "Rad etish" (izoh majburiy),
  `returned` sales ro'yxatida ajralib turadi + "Qayta yuborish"; tarix —
  javobdagi `events[]` (TLD timeline ko'rinishida);
- Didox ikki qadam (B3/F3): shartnoma chizig'i endi
  `Qoralama → Bugalter → Didox → Admin → To'lov → Yetkazish → Yakun`;
  bitta tasdiq oynasi ikkiga bo'linadi — "Didoxga yuborildi" (raqam
  kiritiladigan oyna, `POST …/send-didox/`) va "Didox tasdiqladi"
  (`POST …/confirm-didox/`); yangi holat `pending_didox` uchun yorliq/rang;
- oldindan to'lov foizi (B14): input faqat `draft`/`rejected` da faol —
  keyin backend 400 beradi;
- roadmap (B8/F4) TAYYOR: `GET …/roadmap/` uch kirish nuqtasi, bitta javob
  — yangi `src/modules/workflow/` moduli, bitta komponent uch detalda,
  `PageHeader`dan keyin sahifaning asosiy bloki (yon panel emas). Front
  faqat `tone` → CSS klass va `document.type` → marshrut qiladi; ro'yxat
  qisqarmaydi (18 qadam), havola faqat `can_open: true` da, pul yo'q.
  Ranglar: success/warning/danger/muted + `cancelled` (chizilgan matn, ✕);
  faqat joriy qadam fon oladi; `blocked` kulrang (qulf nishoni bilan);
- BACKEND B1–B17 TO'LIQ TAYYOR — F1–F11 ishlarini boshlash mumkin
  (tartib: F1·F2·F6·F10 → F3·F9·F11 → F4·F5·F7·F8).

---

## Eslatma: oxirgi backend o'zgarishlari (allaqachon serverda)

| Nima | Frontga ta'siri |
|---|---|
| Login throttle | 429 kelsa: "Urinishlar ko'payib ketdi, bir daqiqadan keyin urining" |
| Fayl yuklash cheklovi | 400 dagi `file` xabarini ko'rsating; inputga `accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx"` |
| Bitta ombor | hech qayerda `warehouse` yuborish shart emas, ombor selectlari olib tashlanadi |
| Zanjir bildirishnomalari | TLD va shartnoma tasdiq zanjirining har bosqichida keyingi bosqich egasiga xabar tushadi (bugalter tasdig'ida adminga ham) — qo'ng'iroqcha `/notifications/` ni polling qilsa yetadi, frontda qo'shimcha ish yo'q |

To'liq o'zgarishlar tarixi: [12-CHANGELOG-TZ-2.1.md](12-CHANGELOG-TZ-2.1.md).
