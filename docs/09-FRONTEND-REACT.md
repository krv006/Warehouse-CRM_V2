# 09 — Frontend (React) integratsiya qo'llanmasi

Backend to'liq tayyor va **serverda ishlab turibdi**: **87 endpoint**, 100 test,
OpenAPI sxemasi xatosiz. Ishchi manzil: https://ombor.thesofmebel.uz/api/docs/
Bu fayl — frontend yozish uchun texnik kontrakt. Ekranlar bo'yicha batafsil topshiriq:
[11-FRONTEND-SCREENS.md](11-FRONTEND-SCREENS.md).

| Narsa | Qiymat |
|---|---|
| Baza URL | `https://ombor.thesofmebel.uz/api` |
| Swagger | `/api/docs/` |
| OpenAPI | `/api/schema/` |
| Auth | JWT (Bearer), access 12 soat, refresh 7 kun |
| Rollar | `admin`, `bugalter`, `sales`, `buyurtmachi` |
| Til | Backend javoblari va xato matnlari — o'zbekcha |

---

## 1. Loyihani boshlash

```bash
npm create vite@latest frontend -- --template react-ts
```

`.env`:

```
VITE_API_URL=https://ombor.thesofmebel.uz/api
```

Lokal backend bilan ishlaganda `http://127.0.0.1:8000/api` (CORS ochilgan: `localhost:5173`).

TypeScript tiplarini sxemadan avtomatik yarating — qo'lda yozish shart emas:

```bash
npx openapi-typescript https://ombor.thesofmebel.uz/api/schema/ -o src/api/types.ts
```

---

## 2. Autentifikatsiya

```ts
// POST /auth/login/
const { data } = await api.post('/auth/login/', { username, password })
// -> { access, refresh }
```

Har bir so'rovda sarlavha: `Authorization: Bearer <access>`

`401` kelganda `POST /auth/refresh/ { refresh }` bilan yangilang. **Rotatsiya yoqilgan** —
javobda yangi `refresh` ham keladi, uni ham saqlang. Refresh ham `401` bersa → login sahifasi.

Tavsiya etiladigan axios interceptor:

```ts
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const { data } = await axios.post(`${API}/auth/refresh/`, {
        refresh: localStorage.getItem('refresh'),
      })
      localStorage.setItem('access', data.access)
      if (data.refresh) localStorage.setItem('refresh', data.refresh)
      original.headers.Authorization = `Bearer ${data.access}`
      return api(original)
    }
    return Promise.reject(error)
  },
)
```

Kirgan foydalanuvchi: `GET /users/me/` → `{ id, username, first_name, last_name, role, role_display, language, phone }`.
**Menyu va tugmalar `role` bo'yicha yig'iladi.**

---

## 3. Rollar va ekranlar matritsasi

| Bo'lim | admin | bugalter | sales | buyurtmachi |
|---|:--:|:--:|:--:|:--:|
| Dashboard | ✅ | ✅ | ✅ | ✅ |
| Ombor (mahsulot, qoldiq, harakat) | 👁 | 👁 | 👁 | 👁 |
| Configurator | ✅ | ✅ | ✅ | ✅ |
| ACT | ✅ yozadi | 👁 | 👁 | 👁 |
| Clients | ✅ yozadi | 👁 | ✅ yozadi | ✅ yozadi |
| Leads / Shartnomalar | ✅ | 👁 + tasdiq | ✅ yozadi | 👁 |
| To'ldirish (Buyurtmachi) | ✅ | 👁 + tasdiq/to'lov | ⛔ | ✅ yozadi |
| Kirim (purchases) | ✅ | ✅ | ⛔ | 👁 |
| Kassa, qarzlar | ✅ | ✅ | ⛔ | ⛔ |
| Xarajat so'rovlari | ✅ tasdiq | ✅ so'raydi | ⛔ | ⛔ |
| Foydalanuvchilar | ✅ | ⛔ | ⛔ | ⛔ |
| Audit (activity-logs) | ✅ | ⛔ | ⛔ | ⛔ |

👁 = faqat o'qish (GET ishlaydi, yozishda `403`) · ⛔ = GET ham `403`.

**Sales uchun muhim:** kassa, qarz, xarajat, kirim va to'ldirish bo'limlari umuman
ochilmaydi — bu menyu bandlarini sales uchun ko'rsatmang (TZ 8.3).

**Ombor bo'limi hamma uchun faqat o'qish:** "Mahsulot qo'shish" tugmasi umuman
bo'lmasin. Yangi mahsulot Buyurtmachining to'ldirish buyurtmasida `product_name`
yozilganda paydo bo'ladi (TZ 7), qoldiq esa Kirim/Chiqim orqali o'zgaradi.

**Muhim:** UI ruxsatni yashirish uchun ishlatiladi, lekin backend baribir tekshiradi —
`403` javobini har doim ushlab, tushunarli xabar chiqaring.

---

## 4. Umumiy API qoidalari

### Sahifalash

Barcha ro'yxatlar:

```json
{ "count": 42, "next": "...?page=2", "previous": null, "results": [ ... ] }
```

Parametrlar: `?page=2`, `?search=matn`, `?ordering=-created_at` + har bo'limning filtrlari.

### Xatolar

| Kod | Ma'nosi | UI |
|---|---|---|
| `400` | Validatsiya | maydon xatolari (`{"passport": "..."}`) yoki `{"detail": "..."}` |
| `401` | Token eskirgan | refresh, bo'lmasa login |
| `403` | Rol ruxsat bermaydi | `{"detail": "..."}` matnini ko'rsating |
| `404` | Topilmadi | |

Ba'zi 400 javoblar qo'shimcha kontekst beradi — masalan to'lovda:

```json
{
  "detail": "Kassada yetarli pul yo'q.",
  "total": "1400000.00",
  "cash_available": "500000.00",
  "suggested_debt": "900000.00"
}
```

Bularni forma ichida ko'rsating (`suggested_debt` ni tugmaga default qiymat qilib qo'ying).

### Sana va pul

- Sana: `YYYY-MM-DD`, vaqt: ISO 8601 (`Asia/Tashkent`)
- Pul: string ko'rinishidagi decimal (`"1500000.00"`) — hisob-kitobda `Number()` emas,
  `decimal.js` yoki string bilan ishlashni tavsiya qilamiz

---

## 5. Muddat va rang kontrakti (juda muhim)

Shartnoma, qarz va yetkazib berish muddatlari uchun rangni **backend hisoblaydi** —
frontend uni faqat chizadi.

`GET /contracts/{id}/timeline/`:

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
  "points": [
    { "date": "2026-08-27", "days_left": 90, "color": "green" },
    { "date": "2026-08-28", "days_left": 89, "color": "green" }
  ]
}
```

| `color` | Ma'nosi | Tavsiya etilgan rang |
|---|---|---|
| `green` | Muddat boshi | `#16a34a` |
| `yellow` | Oxirgi uchdan bir | `#f59e0b` |
| `red` | Oxirgi 10 kun yoki muddat o'tgan | `#dc2626` |
| `grey` | Sanoq hali boshlanmagan | `#9ca3af` |

Bir xil `points` formatini beradigan endpointlar:

- `GET /contracts/{id}/timeline/` — shartnoma to'lov muddati
- `GET /purchases/{id}/timeline/` — import kunlari
- `GET /replenishments/{id}/timeline/` — yetkazib berish bosqichlari + qarz muddati

Dashboard uchun qisqa ro'yxatlar: `GET /contracts/deadlines/`, `GET /purchases/in-transit/`.

---

## 6. Modul bo'yicha asosiy oqimlar

### 6.1 Shartnoma (Sales)

```
draft → [submit] → pending_bugalter → [approve] → pending_admin
      → [approve] → approved → [confirm-payment] → active → completed
```

| Amal | Endpoint | Kim |
|---|---|---|
| Yaratish | `POST /contracts/` (`items` bilan) | sales |
| Yuborish | `POST /contracts/{id}/submit/` | sales |
| Tasdiqlash | `POST /contracts/{id}/approve/` | avval bugalter, keyin admin |
| Rad etish | `POST /contracts/{id}/reject/` | bugalter / admin |
| To'lovni tasdiqlash | `POST /contracts/{id}/confirm-payment/` | bugalter |

Tugmalarni `status` + `role` juftligi bo'yicha ko'rsating:

```ts
const canApprove =
  (status === 'pending_bugalter' && (role === 'bugalter' || role === 'admin')) ||
  (status === 'pending_admin' && role === 'admin')
```

**Narx ko'rinishi:** `items[].unit_price` va `items[].subtotal` faqat `sales` va `admin`
javobida bo'ladi. Bugalter uchun bu maydonlar **umuman kelmaydi** — jadval ustunini shartli chizing:

```tsx
{'unit_price' in item && <td>{item.unit_price}</td>}
```

**Komissiya foizi:** `prepayment_percent` bo'sh yuborilsa backend o'zi qo'yadi
(1 mlrd dan kam → 30%, ko'p → 15%). Formada ko'rsating va tahrirlashga ruxsat bering.

### 6.2 Omborni to'ldirish (Buyurtmachi) — yangi

```
draft → [submit] → pending_bugalter → [approve] → pending_admin → [approve]
      → approved → [pay] → ordered → (events: shipped/customs/cleared) → [receive] → delivered
```

| Amal | Endpoint | Kim |
|---|---|---|
| Yetishmayotganlar ro'yxati | `GET /replenishments/low-stock/?warehouse=1` | hamma |
| Ro'yxatdan hisob yaratish | `POST /replenishments/from-low-stock/` | buyurtmachi |
| Narx/logistika kiritish | `PATCH /replenishments/{id}/`, `/replenishment-items/{id}/` | buyurtmachi (qoralamada), admin (doim) |
| Yuborish | `POST /replenishments/{id}/submit/` | buyurtmachi |
| Tekshirish/tasdiqlash | `POST /replenishments/{id}/approve/` | bugalter → admin |
| To'lash | `POST /replenishments/{id}/pay/` | bugalter |
| Bosqich qo'shish | `POST /replenishments/{id}/events/` | buyurtmachi / bugalter |
| Omborga kirim | `POST /replenishments/{id}/receive/` | buyurtmachi / bugalter |

**Admin oynasi** uchun har bir hisobda tayyor maydonlar bor:

```json
{
  "items_total": "1200000.00",
  "logistics_cost": "150000.00",
  "other_cost": "50000.00",
  "total_amount": "1400000.00",
  "cash_available": "500000.00",
  "shortfall": "900000.00"
}
```

`shortfall > 0` bo'lsa — "Pul yetmadi, {shortfall} qarzga o'tqazilsinmi?" degan tasdiq oynasi
chiqaring va `POST /replenishments/{id}/pay/` ni `{"debt_amount": "900000"}` bilan yuboring
(bo'sh yuborilsa backend o'zi hisoblaydi).

Qarz muddati: mahsulot omborga kirim qilingan kundan **60 kun**, rang kodi shartnoma bilan bir xil.

### 6.3 Configurator

| Amal | Endpoint |
|---|---|
| Yaratish | `POST /configurations/` (`items` bilan) |
| Ombor tekshiruvi | `GET /configurations/{id}/stock-check/` |
| Yakunlash | `POST /configurations/{id}/finalize/` |
| Excel | `GET /configurations/{id}/export-excel/` |
| Buyurtmaga biriktirish | `POST /configurations/{id}/attach/` |

Yangi narxlash mantig'i (TZ 6.2) frontendda shunday ko'rinadi:

```json
{
  "ready_variant": { "id": 12, "sku": "HP-880-V01", "price": "5500000.00" },
  "items_total": "5500000.00",
  "total_price": "5500000.00",
  "items": [
    { "component_name": "SSD 1 TB", "unit_price": "1500000.00", "needs_price": false,
      "available": 5, "shortage": 0, "source": "stock" },
    { "component_name": "GPU 32", "unit_price": "0.00", "needs_price": true,
      "available": 0, "shortage": 1, "source": "purchase" }
  ]
}
```

- `unit_price` bo'sh yuborilsa — backend ombordagi narxni o'zi qo'yadi
- `needs_price: true` — qatorni **qizil** belgilang, narx kiritilmaguncha "Yakunlash" tugmasi o'chiq
- `source: "purchase"` — "kirim qilinishi kerak" belgisi
- `ready_variant` bo'lsa — "Bu konfiguratsiya omborda bor" bandi va uning narxi ko'rsatiladi
  (`total_price` shu narxni oladi)
- `finalize` dan keyin yangi variant omborga alohida mahsulot bo'lib qo'shiladi

Excel yuklab olish:

```ts
const res = await api.get(`/configurations/${id}/export-excel/`, { responseType: 'blob' })
const url = URL.createObjectURL(res.data)
```

### 6.4 Kassa

| Amal | Endpoint |
|---|---|
| Hisobot | `GET /cash-transactions/summary/` |
| Yacheyka qo'shish | `POST /cash-categories/` |
| Qarzlar | `GET /loans/` (filtr: `?source=supplier`), `POST /loans/{id}/repay/` |
| Xarajat so'rovi | `POST /expense-requests/` → admin `approve` / `reject` |

---

## 7. Client formasi

`type` tanlanganda maydonlar to'liq almashadi:

| `individual` | `legal` |
|---|---|
| `full_name` * | `company_name` * |
| `passport` * (unique) | `inn` * (unique) |
| `jshshir` * (unique) | `jshshir` * (unique) |
| `phone` * (unique) | `mfo` * |
| `email` | `bank_name` * |
| `note` | `account_number` * (unique) |
| | `director_name` * |
| | `phone` * (unique) |
| | `email`, `address`, `note` — ixtiyoriy |

Backend har bir yetishmayotgan maydonni alohida qaytaradi:

```json
{ "mfo": "Yuridik shaxs uchun MFO majburiy.", "account_number": "..." }
```

Bularni to'g'ridan-to'g'ri forma xatolariga bog'lang.

---

## 8. Dashboard

`GET /dashboard/` — bitta so'rovda hamma narsa:

```json
{
  "kassa": { "income_total", "expense_total", "balance",
             "income_by_category": [], "expense_by_category": [] },
  "kirim": { "by_type": [], "in_transit": 2 },
  "sales": { "contracts_by_status": [], "leads_by_stage": [], "monthly_income": [] },
  "clients": { "total", "individual", "legal" },
  "ombor": { "product_count", "low_stock": [] },
  "deadlines": [],
  "notifications": []
}
```

Grafiklar uchun massivlar tayyor holda keladi — qo'shimcha hisoblash shart emas.

---

## 9. Eslatmalar (notification)

- `GET /notifications/` — o'ziga tegishli + umumiy eslatmalar
- `POST /notifications/{id}/mark-read/`
- `level`: `info` / `warning` / `danger` → ikonka va rang

Eslatmalar backendda kunlik `check_deadlines` komandasi bilan yaratiladi
(shartnoma, qarz va import muddatlari).

---

## 10. Tavsiya etiladigan stack

| Ehtiyoj | Tavsiya |
|---|---|
| So'rovlar | TanStack Query (kesh + invalidatsiya) |
| HTTP | axios + interceptor (yuqorida) |
| Formalar | React Hook Form + zod |
| Jadval | TanStack Table (server-side pagination) |
| Grafik | Recharts (`points` massivi to'g'ridan-to'g'ri mos keladi) |
| Rollar | `useAuth()` konteksti + `<RequireRole roles={['admin']}>` |

Ekranlar ro'yxati, har bir sahifaning maydonlari va holatlari:
**[11-FRONTEND-SCREENS.md](11-FRONTEND-SCREENS.md)**
