# 03 — Rollar va ruxsatlar

## Rollar

| Rol | `role` qiymati | TZ dagi vazifasi |
|---|---|---|
| Administrator | `admin` | Hamma narsani ko'radi va nazorat qiladi, ACT kiritadi, shartnomani oxirgi tasdiqlaydi, bugalterning har bir xarajatiga ruxsat beradi |
| Bugalter | `bugalter` | Hujjatlar, pul kirdi-chiqdisi, shartnomaning birinchi tasdig'i, pul kelganini tasdiqlash |
| Sales | `sales` | Zakaz shakllantiradi, configurator qiladi, client qo'shadi, sotuv narxini ko'radi |
| Buyurtmachi | `buyurtmachi` | Omborda yetishmayotgan mahsulotlarni to'ldiradi: ta'minotchidan narx, logistika xarajati, yetkazib berish kuzatuvi |

`is_superuser = True` bo'lgan foydalanuvchi ham admin sifatida qaraladi
(`User.is_admin` property — `apps/accounts/models/user.py`).

## Permission klasslari

`apps/accounts/permissions.py`:

| Klass | O'qish (GET) | Yozish (POST/PUT/PATCH/DELETE) |
|---|---|---|
| `IsAdmin` | faqat admin | faqat admin |
| `IsAdminOrReadOnly` | barcha login qilganlar | faqat admin |
| `IsAdminOrBugalter` | barcha login qilganlar | admin, bugalter |
| `IsAdminOrSales` | barcha login qilganlar | admin, sales |
| `IsAdminOrSupplier` | barcha login qilganlar | admin, buyurtmachi |
| `CanManageClients` | barcha login qilganlar | admin, sales, buyurtmachi |
| `FinanceAccess` | **admin, bugalter** | admin, bugalter |
| `PurchaseAccess` | **admin, bugalter, buyurtmachi** | admin, bugalter |
| `ProcurementAccess` | **admin, bugalter, buyurtmachi** | admin, buyurtmachi |
| `ProcurementSharedAccess` | admin, bugalter, buyurtmachi | admin, buyurtmachi, bugalter |

Hammasi `RoleAccess` asosida: `read_roles` / `write_roles` ro'yxatlari, admin esa doim o'tadi.
Qalin yozilgan qatorlar — **sales umuman ko'ra olmaydigan** bo'limlar (TZ 8.3).

Global default: `IsAuthenticated` (`root/settings/rest.py`) — login qilmagan hech kim hech nimani ko'rmaydi.

## Endpointlar bo'yicha ruxsat jadvali

| Endpoint | O'qish | Yozish | Maxsus |
|---|---|---|---|
| `/api/dashboard/` | hamma | — | |
| `/api/users/` | admin | admin | `/users/me/` — hamma |
| `/api/activity-logs/` | **admin** | — | audit |
| `/api/notifications/` | o'ziniki + umumiy | — | `mark-read` |
| `/api/clients/` | hamma | admin, sales, buyurtmachi | bugalter faqat o'qiydi |
| `/api/warehouses/`, `/products/`, `/product-specs/`, `/stocks/`, `/movements/` | hamma | **hech kim** | katalog faqat o'qish uchun; yangi mahsulot buyurtma orqali qo'shiladi |
| `/api/acts/` | hamma | **faqat admin** | ACT ni admin kiritadi |
| `/api/configurations/`, `/configuration-items/` | hamma | hamma | configurator hammaga ochiq (TZ 6.5) |
| `/api/leads/`, `/contracts/`, `/contract-items/` | hamma | admin, sales | narx faqat sales va adminga ko'rinadi |
| `/api/contract-payments/` | hamma | admin, bugalter | |
| `/api/contract-approvals/` | hamma | — | faqat o'qish |
| `/api/purchases/`, `/purchase-items/` | **admin, bugalter, buyurtmachi** | admin, bugalter | sales — 403 |
| `/api/replenishments/` va qatorlari | **admin, bugalter, buyurtmachi** | admin, buyurtmachi | `approve`/`reject`/`pay` — admin, bugalter; `receive`/`events` — buyurtmachi va bugalter; sales — 403 |
| `/api/cash-categories/`, `/cash-transactions/`, `/loans/`, `/expense-requests/` | **admin, bugalter** | admin, bugalter | `expense-requests/approve\|reject` — **faqat admin**; sales — 403 |

### Sales roli aynan nimani ko'radi (TZ 8.3)

| Bo'lim | Sales |
|---|---|
| Dashboard | ✅ ko'radi |
| Mijozlar | ✅ ko'radi va qo'shadi |
| Leads (og'zaki kelishuv) | ✅ ko'radi va yuritadi |
| Shartnomalar | ✅ tuzadi, yuboradi, **sotuv narxini ko'radi** |
| Configurator | ✅ to'liq ishlaydi |
| ACT | 👁 faqat ko'radi |
| Ombor (mahsulot, qoldiq, harakat) | 👁 **faqat ko'radi** — bu bo'lim hamma uchun faqat o'qish |
| Eslatmalar | ✅ o'ziniki |
| Kassa, qarzlar, xarajat so'rovlari | ⛔ **403** |
| Kirim (purchases) | ⛔ **403** |
| To'ldirish (buyurtmachi bo'limi) | ⛔ **403** |
| Foydalanuvchilar, Audit | ⛔ **403** |

## Shartnoma zanjiridagi rol tekshiruvi

`apps/sales/services.py` ichida qo'shimcha qat'iy tekshiruv bor — endpoint ruxsatidan tashqari:

| Amal | Kim bajara oladi | Aks holda |
|---|---|---|
| `submit` (draft → pending_bugalter) | sales, admin | `403` |
| `approve` (pending_bugalter → pending_admin) | bugalter, admin | `403` |
| `approve` (pending_admin → approved) | **faqat admin** | `403` — bugalter ham o'tolmaydi |
| `confirm-payment` (approved → active) | bugalter, admin | `403` |

## To'ldirish (Buyurtmachi) zanjiridagi tekshiruv

`apps/procurement/services.py`:

| Amal | Kim bajara oladi |
|---|---|
| `from-low-stock`, `submit` | buyurtmachi, admin |
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
