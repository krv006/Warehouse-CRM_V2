# Hujjatlar

Ombor CRM (Warehouse CRM V2) loyihasining to'liq hujjatlari.

| № | Fayl | Nima haqida | Kimga |
|---|---|---|---|
| 01 | [01-ARCHITECTURE.md](01-ARCHITECTURE.md) | Papka tuzilishi, ilovalar, qatlamlar, marshrutlar qanday yig'ilishi | Backend dasturchi |
| 02 | [02-BUSINESS-RULES.md](02-BUSINESS-RULES.md) | TZ qoidalari: Kirim, Chiqim, Kassa, foizlar (30/15), ranglar, ACT | Hamma |
| 03 | [03-ROLES-PERMISSIONS.md](03-ROLES-PERMISSIONS.md) | Admin / Bugalter / Sales — kim nima qila oladi | Hamma |
| 04 | [04-DATA-MODEL.md](04-DATA-MODEL.md) | Barcha modellar, maydonlar, ER diagramma | Backend dasturchi |
| 05 | [05-API.md](05-API.md) | Endpointlar, so'rov va javob namunalari | Frontend + backend |
| 06 | [06-WORKFLOWS.md](06-WORKFLOWS.md) | Shartnoma, configurator, kirim, kassa jarayonlari (diagrammalar) | Hamma |
| 07 | [07-CODE-STYLE.md](07-CODE-STYLE.md) | Kod yozish qoidalari — **majburiy** | Backend dasturchi |
| 08 | [08-TESTING.md](08-TESTING.md) | Testlar, komandalar, qamrov | Backend dasturchi |
| 09 | [09-FRONTEND-REACT.md](09-FRONTEND-REACT.md) | React integratsiyasi: auth, rollar, chartlar, formalar | Frontend dasturchi |
| 10 | [10-DEPLOY.md](10-DEPLOY.md) | Serverga o'rnatish: Docker (bitta komanda) yoki systemd + nginx | DevOps / server |
| 11 | [11-FRONTEND-SCREENS.md](11-FRONTEND-SCREENS.md) | Ekranlar bo'yicha topshiriq: har bir sahifa, endpoint, maydon, holat | Frontend dasturchi |
| 12 | [12-CHANGELOG-TZ-2.1.md](12-CHANGELOG-TZ-2.1.md) | TZ 2.1 da nima o'zgardi (breaking o'zgarishlar) | Frontend + backend |

Boshlash: [../README.md](../README.md) · AI yordamchi uchun qisqa qoidalar: [../CLAUDE.md](../CLAUDE.md)

## Qayerdan boshlash

**Loyihaga yangi qo'shildingizmi?**
`README.md` → `02-BUSINESS-RULES.md` → `03-ROLES-PERMISSIONS.md` → `01-ARCHITECTURE.md`

**Backend yozasizmi?**
`07-CODE-STYLE.md` → `01-ARCHITECTURE.md` → `04-DATA-MODEL.md` → `08-TESTING.md`

**Frontend yozasizmi?**
`12-CHANGELOG-TZ-2.1.md` → `09-FRONTEND-REACT.md` → `11-FRONTEND-SCREENS.md` → `05-API.md` → `03-ROLES-PERMISSIONS.md`

**Biznes qoidani tekshirmoqchimisiz?**
`02-BUSINESS-RULES.md` → `06-WORKFLOWS.md`

**Serverga qo'ymoqchimisiz?**
`10-DEPLOY.md`
