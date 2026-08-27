# 09 — React frontend uchun qo'llanma

Backend tayyor, frontend keyingi bosqich. Bu fayl React tomonini yozishda kerak bo'ladigan hamma narsani beradi.

## Sozlash

Backend CORS'da ruxsat berilgan manzillar: `http://localhost:5173`, `http://127.0.0.1:5173` (Vite default).

```bash
npm create vite@latest frontend -- --template react
```

`.env`:
```
VITE_API_URL=http://127.0.0.1:8000/api
```

Boshqa portda ishlasangiz, `root/settings.py` dagi `CORS_ALLOWED_ORIGINS` ga qo'shing.

## Autentifikatsiya

```js
// login
const { data } = await axios.post(`${API}/auth/login/`, { username, password })
localStorage.setItem('access', data.access)
localStorage.setItem('refresh', data.refresh)

// har bir so'rov
axios.defaults.headers.common.Authorization = `Bearer ${localStorage.getItem('access')}`

// 401 bo'lsa
const { data } = await axios.post(`${API}/auth/refresh/`, { refresh })
```

Access — 12 soat, refresh — 7 kun (rotatsiya yoqilgan: har `refresh` da yangi refresh keladi).

Kirgan foydalanuvchi ma'lumoti: `GET /users/me/` → `{id, username, role, language, ...}`.
Menyuni **`role`** bo'yicha yig'ing (`admin` / `bugalter` / `sales`).

## Rol bo'yicha ekranlar

| Ekran | admin | bugalter | sales |
|---|:--:|:--:|:--:|
| Dashboard | ✅ | ✅ | ✅ |
| Clients | ✅ (yozadi) | 👁 faqat ko'radi | ✅ (yozadi) |
| Ombor (products, stocks, movements) | ✅ | ✅ | ✅ |
| Configurator | ✅ | ✅ | ✅ |
| ACT | ✅ (yozadi) | 👁 | 👁 |
| Kirim (purchases) | ✅ | ✅ | 👁 |
| Leads / Contracts | ✅ | 👁 + approve | ✅ |
| Kassa, qarzlar | ✅ | ✅ | 👁 |
| Xarajat so'rovlari | ✅ approve/reject | ✅ so'raydi | 👁 |
| Audit (activity-logs) | ✅ | ⛔ | ⛔ |

To'liq jadval: [03-ROLES-PERMISSIONS.md](03-ROLES-PERMISSIONS.md).

## Ro'yxatlar bilan ishlash

Barcha ro'yxat endpointlari sahifalangan:

```json
{"count": 42, "next": "...?page=2", "previous": null, "results": [...]}
```

Parametrlar: `?page=2`, `?search=matn`, `?ordering=-created_at`, plus har bir endpointning filtrlari
([05-API.md](05-API.md)).

## Line chart (muddat sanog'i)

Shartnoma: `GET /contracts/{id}/timeline/`, import: `GET /purchases/{id}/timeline/`.

```json
{
  "days_left": 90, "days_passed": 0, "deadline": "2026-11-25", "color": "green",
  "points": [{"date": "2026-08-27", "days_left": 90, "color": "green"}]
}
```

`points` massivini to'g'ridan-to'g'ri chartga bering — rang backendda hisoblangan:

| Rang | Ma'nosi |
|---|---|
| `green` | muddat boshida, xotirjam |
| `yellow` | oxirgi 30% ga kirdi |
| `red` | oxirgi 10 kun yoki muddat o'tib ketgan |
| `grey` | sanoq hali boshlanmagan |

Dashboard uchun qisqa ro'yxat: `GET /contracts/deadlines/`.

## Dashboard

`GET /dashboard/` bitta so'rovda: `kassa`, `kirim`, `sales`, `clients`, `ombor`, `deadlines`, `notifications`.
Grafiklar uchun tayyor massivlar: `kassa.income_by_category`, `kassa.expense_by_category`,
`sales.monthly_income`, `sales.contracts_by_status`, `sales.leads_by_stage`, `kirim.by_type`.

## Formalar

### Client
`type` ni tanlaganda maydonlar almashadi:

| `individual` | `legal` |
|---|---|
| `full_name`, `passport`, `jshshir`, `phone` | `company_name`, `inn`, `jshshir`, `director_name`, `address`, `phone` |

Backend 400 bilan maydon nomi + o'zbekcha matn qaytaradi — to'g'ridan-to'g'ri forma xatosiga qo'ying.

### Shartnoma
`items` massivi bilan yuboriladi. `total_amount` bo'sh bo'lsa qatorlardan hisoblanadi,
`prepayment_percent` bo'sh bo'lsa 30% / 15% avtomatik qo'yiladi — foizni ko'rsatib, o'zgartirishga ruxsat bering.

> Bugalter shartnomani ochganda `items[].unit_price` javobda **bo'lmaydi** — UI shunga tayyor bo'lsin
> (narx ustunini yashiring, umumiy summa ko'rinadi).

### Configurator
1. `base_product` tanlanadi → `GET /products/{id}/` javobidagi `specs` zavod tarkibini beradi.
2. Foydalanuvchi qatorlarni o'zgartiradi → `POST /configurations/`.
3. `GET /configurations/{id}/stock-check/` — qaysi butlovchi ombordan, qaysi biri kirim qilinishi kerakligini ko'rsatadi.
4. ACT tanlanadi → `POST /{id}/finalize/`.
5. `GET /{id}/export-excel/` — faylni yuklab olish:

```js
const res = await axios.get(`${API}/configurations/${id}/export-excel/`, { responseType: 'blob' })
const url = URL.createObjectURL(res.data)
```

## Xatolarni ko'rsatish

| Kod | Ma'nosi | UI |
|---|---|---|
| 400 | Validatsiya | maydon xatolari (`{"passport": "..."}`) yoki `{"detail": "..."}` |
| 401 | Token muddati tugagan | refresh, bo'lmasa login sahifasi |
| 403 | Rol ruxsat bermaydi | "Sizda bu amal uchun ruxsat yo'q" |
| 404 | Topilmadi | |

Xato matnlari backendda **o'zbekcha** — to'g'ridan-to'g'ri ko'rsatsa bo'ladi.

## Endpointlarning tayyor tipi

`GET /api/schema/` — OpenAPI 3. TypeScript tiplarini avtomatik yaratish:

```bash
npx openapi-typescript http://127.0.0.1:8000/api/schema/ -o src/api/types.ts
```
