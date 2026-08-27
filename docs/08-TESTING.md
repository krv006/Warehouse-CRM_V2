# 08 — Testlar

## Ishga tushirish

```bash
.venv/Scripts/python.exe manage.py test apps
```

Bitta ilova:

```bash
.venv/Scripts/python.exe manage.py test apps.sales
```

Bitta klass yoki metod:

```bash
.venv/Scripts/python.exe manage.py test apps.sales.tests.test_contract_flow.ContractFlowTests.test_full_approval_chain
```

Tezroq (parallel):

```bash
.venv/Scripts/python.exe manage.py test apps --parallel
```

Hozirgi holat: **146 ta test, hammasi OK**.

---

## Qamrov

| Fayl | Nimani tekshiradi |
|---|---|
| `apps/accounts/tests/test_user_api.py` | rol propertylari, default rol `sales`, `/users/me/`, foydalanuvchilar ro'yxati faqat adminga, parol bilan yaratish |
| `apps/core/tests/test_seed_demo.py` | seed_demo: modul bo'yicha sonlar, shartnoma bosqichlari to'liq qamrovi, faol shartnoma qizil zonada, kirim turlari, haqiqiy jarayondan o'tgan ta'minotchi qarzi (5 mln), yetishmayotgan mahsulot misollari, kassa musbat, idempotentlik, dashboard boyligi |
| `apps/core/tests/test_docs_consistency.py` | Hujjatlar kod bilan mos turishi: har bir endpoint 05-API.md da, har bir permission sinfi 03-ROLES da yozilgani, o'chirilgan nomlar qolmagani, README dagi endpoint soni haqiqiy songa mosligi |
| `apps/accounts/tests/test_role_matrix.py` | TZ 8: 4 rol × 15 bo'lim o'qish matritsasi va 11 bo'lim yozish matritsasi; sales uchun kassa/kirim/to'ldirish yopiqligi va ombor faqat o'qish uchun ekani |
| `apps/accounts/tests/test_jwt_auth.py` (`DemoUsersLoginTests`) | 4 rolning har biri JWT bilan kirishi, `/users/me/` dan o'z rolini olishi, login'dan keyin rol bo'yicha ruxsatlar (audit faqat adminga, replenishments buyurtmachiga, kassa bugalterga) |
| `apps/accounts/tests/test_jwt_auth.py` | login token juftligini qaytarishi, noto'g'ri parol 401, access token bilan himoyalangan endpoint ochilishi, refresh rotatsiyasi, token muddatlari sozlamadan |
| `apps/clients/tests/test_client_api.py` | jismoniy shaxs uchun passport/JSHSHIR majburiyligi, yuridik uchun INN/manzil, telefon unique, bugalter client qo'sha olmasligi |
| `apps/inventory/tests/test_stock_services.py` | `in` qoldiqni oshirishi, `out` kamaytirishi, `adjust` yakuniy qoldiqni qo'yishi, `is_low_stock`, movement API orqali qoldiq va `created_by` |
| `apps/configurator/tests/test_configuration.py` | `CFG-` raqami, omborda bor/yo'q (`stock` / `purchase`), umumiy narx, ACT'siz `finalize` bo'lmasligi, buyurtmaga biriktirish, Excel eksport, ACT faqat adminga |
| `apps/sales/tests/test_contract_flow.py` | `SHT-` raqami, 30% va 15% foizlar, qo'lda foiz, to'liq approve zanjiri, bugalter admin bosqichini o'tolmasligi, sales tasdiqlay olmasligi, to'lov sanoqni boshlashi va kassaga tushishi, timeline ranglari, narx bugalterdan yashirilishi |
| `apps/purchases/tests/test_purchase_flow.py` | `KIR-` raqami, bojxona+soliq bilan jami, `expected_at` hisoblanishi, `receive` ombor va kassaga ta'siri, takroriy `receive` xatosi, yo'ldagilar ro'yxati, sales kirim qo'sha olmasligi |
| `apps/finance/tests/test_kassa.py` | tizim kategoriyalari, yo'nalish kategoriyadan olinishi, `summary` balansi, yangi yacheyka qo'shish, qarz kirimi va deadline, qarz yopilishi, xarajat so'rovi admin ruxsati bilan, rad etish |
| `apps/procurement/tests/test_replenishment_flow.py` | TZ 7: yetishmayotganlar ro'yxati, hisob shakllantirish, narxsiz yuborishning bloklanishi, buyurtmachi→bugalter→admin zanjiri, pul yetmasa qarzga o'tishi (1 400 000 / 500 000 / 900 000), qarz muddati kirimdan 60 kun, ombor qoldig'i, bojxona bosqichi, admin qatorni tahrirlashi |
| `apps/configurator/tests/test_variant_pricing.py` | TZ 6.2: narx ombordan olinishi, narxsiz qatorning bloklanishi, variant yaratilishi, bir xil tarkibning qayta ishlatilishi, tayyor variant narxi |
| `apps/configurator/tests/test_configuration_request.py` | Sales→Engineer zayavka oqimi: ZVK raqami, take/complete faqat engineerga, sales'ga notification, configuratsiz complete 400 |
| `apps/finance/tests/test_kassa.py` (`LoanRepaidBugTests`) | Qarz bug'i regressiyasi: yangi qarzda repaid=0, qisman/to'liq qaytarish, ortiqcha to'lov va yopiq qarzga 400 |
| `apps/core/tests/test_dashboard_and_audit.py` | dashboard bo'limlari va balans, `ActivityLog` yozilishi, audit faqat adminga, `check_deadlines` eslatmalari va idempotentligi, notification `mark-read` |

---

## Test yozish uslubi

```python
from rest_framework.test import APITestCase

from apps.accounts.models import User


class ContractFlowTests(APITestCase):
    """Sales -> bugalter -> admin -> to'lov zanjiri va muddat sanog'i."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.client.force_authenticate(self.sales)

    def test_full_approval_chain(self):
        ...
```

Qoidalar:

1. Fayl `apps/<app>/tests/test_<nima>.py` ichida (`tests.py` emas).
2. API testlari — `APITestCase` + `self.client.force_authenticate(user)` (JWT token olishning hojati yo'q).
3. Sof model/service testlari — `django.test.TestCase`.
4. Klass va murakkab metodlarga o'zbekcha docstring.
5. Har bir yangi biznes qoida uchun kamida bitta test: foiz, rang, rol ruxsati, qoldiq, status o'tishi.
6. Sana bilan ishlaganda `django.utils.timezone.localdate()` va `timedelta` ishlatiladi — qattiq sana yozilmaydi.

---

## Foydali tekshiruvlar

```bash
.venv/Scripts/python.exe manage.py check
```

```bash
.venv/Scripts/python.exe manage.py makemigrations --check --dry-run
```
Model o'zgargan-u, migratsiya yozilmagan bo'lsa — shu yerda bilinadi.

```bash
.venv/Scripts/python.exe manage.py spectacular --file schema.yml
```
OpenAPI schema xatosiz yig'ilishini tekshiradi (hozir: 0 xato).
