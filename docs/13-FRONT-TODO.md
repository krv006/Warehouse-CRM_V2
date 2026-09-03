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

## Eslatma: oxirgi backend o'zgarishlari (allaqachon serverda)

| Nima | Frontga ta'siri |
|---|---|
| Login throttle | 429 kelsa: "Urinishlar ko'payib ketdi, bir daqiqadan keyin urining" |
| Fayl yuklash cheklovi | 400 dagi `file` xabarini ko'rsating; inputga `accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.xls,.xlsx"` |
| Bitta ombor | hech qayerda `warehouse` yuborish shart emas, ombor selectlari olib tashlanadi |

To'liq o'zgarishlar tarixi: [12-CHANGELOG-TZ-2.1.md](12-CHANGELOG-TZ-2.1.md).
