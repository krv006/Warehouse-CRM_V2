# 03 — Rollar va ruxsatlar

## Rollar

| Rol | `role` qiymati | TZ dagi vazifasi |
|---|---|---|
| Administrator | `admin` | Hamma narsani ko'radi va nazorat qiladi, shartnomani oxirgi tasdiqlaydi, bugalterning har bir xarajatiga ruxsat beradi |
| Bugalter | `bugalter` | Hujjatlar, pul kirdi-chiqdisi, shartnomaning birinchi tasdig'i, pul kelganini tasdiqlash |
| Sales | `sales` | Zakaz shakllantiradi, configurator qiladi, client qo'shadi, sotuv narxini ko'radi |
| Buyurtmachi | `buyurtmachi` | Omborda yetishmayotgan mahsulotlarni to'ldiradi: ta'minotchidan narx, logistika xarajati, yetkazib berish kuzatuvi |
| Engineer | `engineer` | **Configurator tahriri to'liq unda**: sales'dan matnli zayavka oladi, konfiguratsiyani tayyorlaydi, **ACT kiritib yakunlaydi** va salesga topshiradi (§11.1) |

`is_superuser = True` bo'lgan foydalanuvchi ham admin sifatida qaraladi
(`User.is_admin` property — `apps/accounts/models/user.py`).

## Permission klasslari

`apps/accounts/permissions.py`:

| Klass | O'qish (GET) | Yozish (POST/PUT/PATCH/DELETE) |
|---|---|---|
| `IsAdmin` | faqat admin | faqat admin |
| `IsAdminOrBugalter` | barcha login qilganlar | admin, bugalter |
| `IsAdminOrSales` | barcha login qilganlar | admin, sales |
| `CanManageClients` | barcha login qilganlar | admin, sales, buyurtmachi |
| `FinanceAccess` | **admin, bugalter** | admin, bugalter |
| `PurchaseAccess` | **admin, bugalter, buyurtmachi** | admin, bugalter |
| `ProcurementAccess` | admin, bugalter, buyurtmachi, sales | admin, buyurtmachi |
| `ProcurementSharedAccess` | admin, bugalter, buyurtmachi, sales | admin, buyurtmachi, bugalter |
| `ProcurementApprovalAccess` | admin, bugalter, buyurtmachi, sales | admin, sales, bugalter — qaysi bosqichda kim tasdiqlashini servis tekshiradi |
| `ConfiguratorAccess` | barcha login qilganlar | **admin, engineer** |
| `ProductSpecAccess` | barcha login qilganlar | admin, engineer, buyurtmachi |
| `IsOwnerOrAdmin` | aralashmaydi (ko'rinish — `get_queryset()`) | **egasi + admin** — shartnoma/kelishuv/konfiguratsiya va qatorlari (EGALIK §3.4) |
| `UserDirectoryAccess` | **admin, bugalter** — xodimlar ro'yxati (`GET /users/`); yozish bu sinfda umuman yo'q |
| `ProductPricingAccess` | barcha login qilganlar | **admin, bugalter, buyurtmachi** — katalog narx siyosati: `PATCH /products/{id}/` (`sale_price`, `cost_price`, `reorder_level`, `is_active`); buyurtmachi YANGI-OQIM B2 narx so'roviga javoban tannarx kiritadi (§6-B: sotuv narxi yo'q bo'lsa tannarx + `markup_percent` ustama) |
| `ConfigurationRequestAccess` | barcha login qilganlar | admin, sales, engineer |

Hammasi `RoleAccess` asosida: `read_roles` / `write_roles` ro'yxatlari, admin esa doim o'tadi.
Qalin yozilgan qatorlar — **sales umuman ko'ra olmaydigan** bo'limlar (TZ 8.3).

Global default: `IsAuthenticated` (`root/settings/rest.py`) — login qilmagan hech kim hech nimani ko'rmaydi.

## Endpointlar bo'yicha ruxsat jadvali

| Endpoint | O'qish | Yozish | Maxsus |
|---|---|---|---|
| `/api/dashboard/` | hamma | — | `kassa` bloki faqat admin/bugalterga |
| `/api/my-work/`, `/api/sidebar-counts/` | hamma | — | javob so'rovchi roli bo'yicha (EGALIK §2) |
| `/api/company/` | hamma | **faqat admin** | bajaruvchi (o'z firmamiz) rekvizitlari — shartnoma chop etishda ishlatiladi |
| `/api/users/` | **admin, bugalter** (EGALIK §5.3 — "Xodim" filtri, oylik) | **faqat admin** (rol berish) | `/users/me/` — hamma |
| `/api/activity-logs/` | **admin** | — | audit |
| `/api/notifications/` | o'ziniki + umumiy | — | `mark-read` |
| `/api/clients/` | hamma | admin, sales, buyurtmachi | bugalter faqat o'qiydi |
| `/api/warehouses/`, `/stocks/`, `/movements/` | hamma | **hech kim** | faqat o'qish; qoldiq Kirim/Chiqim orqali o'zgaradi |
| `/api/products/` | hamma | **PATCH: admin, bugalter** (§10.2 — narx siyosati) | POST yo'q — yangi mahsulot buyurtma orqali qo'shiladi |
| `/api/reservations/` | hamma | — (avtomatik yoziladi) | §11.4 bron; `release` — **faqat admin**, sabab majburiy |
| `/api/product-specs/` | hamma | **admin, engineer, buyurtmachi** | tayyor model tarkibi (ichidagi configlar) — buyurtmachi kirim qilganda, engineer configurator ishida kiritadi |
| `/api/acts/` | hamma | **engineer** (admin) | §11.1: ACT — tarkibga asos hujjat, uni tarkib egasi (engineer) yuritadi |
| `/api/configurations/`, `/configuration-items/` | hamma | **admin, engineer** | sales configurator ishini qilmaydi — zayavka yuboradi; §11.1: `finalize` va `assemble` ham **engineer** (admin), sales'ga 403 |
| `/api/configuration-requests/` | hamma | admin, sales, engineer | `take`/`complete` — faqat engineer (admin) |
| `/api/leads/`, `/contracts/`, `/contract-items/` | EGALIK §3: sales — **faqat o'ziniki**; bugalter/admin — hammasi (lead: faqat egasi va admin) | egasi (admin) | narx faqat sales va adminga ko'rinadi; boshqaniki 404 |
| `/api/contract-payments/` | hamma | admin, bugalter | |
| `/api/contract-approvals/` | hamma | — | faqat o'qish |
| `/api/purchases/`, `/purchase-items/` | **admin, bugalter, buyurtmachi** | admin, bugalter | sales — 403 |
| `/api/replenishments/` va qatorlari | admin, bugalter, buyurtmachi, sales | admin, buyurtmachi | `approve`/`reject` — bosqichga qarab: **sales (mijoz roziligi) → bugalter → admin** (mijoz buyurtmasidan ochilgan hisobda; oddiy to'ldirishda sales bosqichi yo'q); `pay` — admin, bugalter; `receive`/`events` — buyurtmachi va bugalter |
| `/api/cash-categories/`, `/cash-transactions/`, `/loans/`, `/expense-requests/` | **admin, bugalter** | admin, bugalter | `expense-requests/approve\|reject` — **faqat admin**; sales — 403 |

### Sales roli aynan nimani ko'radi (TZ 8.3)

| Bo'lim | Sales |
|---|---|
| Dashboard | ✅ ko'radi |
| Mijozlar | ✅ ko'radi va qo'shadi |
| Leads (og'zaki kelishuv) | ✅ ko'radi va yuritadi |
| Shartnomalar | ✅ tuzadi, yuboradi, **sotuv narxini ko'radi** — lekin **faqat o'zinikini** (EGALIK §3) |
| Configurator | 👁 ko'radi; **zayavka yuboradi** (`/configuration-requests/`); §11.1: engineer ACT bilan yakunlab tayyor shartnomani topshiradi |
| ACT | 👁 faqat ko'radi — §11.1: ACT engineerga o'tdi |
| Ombor (mahsulot, qoldiq, harakat) | 👁 **faqat ko'radi** — bu bo'lim hamma uchun faqat o'qish |
| Eslatmalar | ✅ o'ziniki |
| Kassa, qarzlar, xarajat so'rovlari | ⛔ **403** |
| Kirim (purchases) | ⛔ **403** |
| To'ldirish (buyurtmachi bo'limi) | 👁 O'Z hisobini (`owner_sales`) **butun yo'l davomida** ko'radi; mijoz bilan kelishib **tasdiqlaydi/qaytaradi** (amal faqat `pending_sales`da) |
| Foydalanuvchilar, Audit | ⛔ **403** |

## Shartnoma zanjiridagi rol tekshiruvi

`apps/sales/services.py` ichida qo'shimcha qat'iy tekshiruv bor — endpoint ruxsatidan tashqari:

| Amal | Kim bajara oladi | Aks holda |
|---|---|---|
| `submit` (draft/rejected → pending_bugalter) | sales, admin | `403` |
| `approve` (pending_bugalter → pending_admin) — §11.2 "Didox qabuli", `didox_number` shu yerda saqlanadi | bugalter, admin | `403` |
| §11.3: summa `admin_approval_threshold` dan **kichik** (UZS) bo'lsa — bugalter tasdig'i bilan to'g'ridan-to'g'ri `approved`, tarixda avtomatik admin yozuvi | — | — |
| `approve` (pending_admin → approved) | **faqat admin** | `403` — bugalter ham o'tolmaydi |
| `confirm-payment` (approved → active) — §11.2 "boshlang'ich to'lov", tarixga `payment` qadami yoziladi | bugalter, admin | `403` |

## To'ldirish (Buyurtmachi) zanjiridagi tekshiruv

`apps/procurement/services.py`:

| Amal | Kim bajara oladi |
|---|---|
| `from-low-stock`, `submit` | buyurtmachi, admin |
| `approve`/`reject` (pending_sales → pending_bugalter) — mijoz buyurtmasidan ochilgan hisobda | **sales**, admin |
| `approve` (pending_bugalter → pending_admin) | bugalter, admin |
| `approve` (pending_admin → approved) | **faqat admin** |
| `pay` | bugalter, admin |
| `events`, `receive` | buyurtmachi, bugalter, admin |
| Qatorni tahrirlash/o'chirish tekshiruvdan keyin | **faqat admin** (TZ 7.1) |

Ya'ni bugalter admin bosqichini "sakrab" o'tolmaydi — bu testlar bilan qopalangan
(`apps/sales/tests/test_contract_flow.py`).

## Yangi foydalanuvchi ochish

```bash
.venv/Scripts/python.exe manage.py createsuperuser
```

Yoki admin sifatida API orqali:

```
POST /api/users/
{
  "username": "bugalter1",
  "password": "kuchli-parol",
  "first_name": "Aziz",
  "role": "bugalter",
  "phone": "+998901234567",
  "language": "uz"
}
```

Default rol — `sales`.


## Sales → Engineer zayavka oqimi

| Amal | Kim | Endpoint |
|---|---|---|
| Zayavka yozish (client xohishi matnda) | sales | `POST /api/configuration-requests/` |
| Ishga olish | engineer | `POST /api/configuration-requests/{id}/take/` |
| Konfiguratsiyani tayyorlash | engineer | configurator (`/configurations/...`) |
| Zayavkani yakunlash (config biriktiriladi) | engineer | `POST /api/configuration-requests/{id}/complete/` |
| Natijani olish, shartnoma boshlash | sales | eslatma keladi; `request.configuration` orqali |
