# 03 — Rollar va ruxsatlar

## Rollar

| Rol | `role` qiymati | TZ dagi vazifasi |
|---|---|---|
| Administrator | `admin` | Hamma narsani ko'radi va nazorat qiladi, ACT kiritadi, shartnomani oxirgi tasdiqlaydi, bugalterning har bir xarajatiga ruxsat beradi |
| Bugalter | `bugalter` | Hujjatlar, pul kirdi-chiqdisi, shartnomaning birinchi tasdig'i, pul kelganini tasdiqlash |
| Sales | `sales` | Zakaz shakllantiradi, configurator qiladi, client qo'shadi, sotuv narxini ko'radi |

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
| `CanManageClients` | barcha login qilganlar | bugalterdan tashqari hamma |

Global default: `IsAuthenticated` (`root/settings.py`) — login qilmagan hech kim hech nimani ko'rmaydi.

## Endpointlar bo'yicha ruxsat jadvali

| Endpoint | O'qish | Yozish | Maxsus |
|---|---|---|---|
| `/api/users/` | admin | admin | `/users/me/` — hamma |
| `/api/clients/` | hamma | admin, sales | bugalter faqat o'qiydi |
| `/api/categories/`, `/warehouses/`, `/products/`, `/product-specs/`, `/stocks/`, `/movements/` | hamma | hamma | ombor bo'limi umumiy |
| `/api/acts/` | hamma | **faqat admin** | ACT ni admin kiritadi |
| `/api/configurations/`, `/configuration-items/` | hamma | hamma | configurator hammaga ochiq |
| `/api/purchases/`, `/purchase-items/` | hamma | admin, bugalter | `receive` — admin, bugalter |
| `/api/leads/` | hamma | admin, sales | |
| `/api/contracts/` | hamma | admin, sales | `submit` — sales; `approve`/`reject`/`confirm-payment` — admin, bugalter |
| `/api/contract-items/` | hamma | admin, sales | narx faqat sales va adminga ko'rinadi |
| `/api/contract-payments/` | hamma | admin, bugalter | |
| `/api/contract-approvals/` | hamma | — | faqat o'qish |
| `/api/cash-categories/`, `/cash-transactions/`, `/loans/`, `/expense-requests/` | hamma | admin, bugalter | `expense-requests/approve|reject` — **faqat admin** |
| `/api/activity-logs/` | **faqat admin** | — | audit |
| `/api/notifications/` | o'ziniki + umumiy | — | `mark-read` |
| `/api/dashboard/` | hamma | — | admin uchun to'liq manzara |

## Shartnoma zanjiridagi rol tekshiruvi

`apps/sales/services.py` ichida qo'shimcha qat'iy tekshiruv bor — endpoint ruxsatidan tashqari:

| Amal | Kim bajara oladi | Aks holda |
|---|---|---|
| `submit` (draft → pending_bugalter) | sales, admin | `403` |
| `approve` (pending_bugalter → pending_admin) | bugalter, admin | `403` |
| `approve` (pending_admin → approved) | **faqat admin** | `403` — bugalter ham o'tolmaydi |
| `confirm-payment` (approved → active) | bugalter, admin | `403` |

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
