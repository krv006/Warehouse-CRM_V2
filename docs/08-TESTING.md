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

Hozirgi holat: **51 ta test, hammasi OK**.

---

## Qamrov

| Fayl | Nimani tekshiradi |
|---|---|
| `apps/accounts/tests/test_user_api.py` | rol propertylari, default rol `sales`, `/users/me/`, foydalanuvchilar ro'yxati faqat adminga, parol bilan yaratish |
| `apps/clients/tests/test_client_api.py` | jismoniy shaxs uchun passport/JSHSHIR majburiyligi, yuridik uchun INN/manzil, telefon unique, bugalter client qo'sha olmasligi |
| `apps/inventory/tests/test_stock_services.py` | `in` qoldiqni oshirishi, `out` kamaytirishi, `adjust` yakuniy qoldiqni qo'yishi, `is_low_stock`, movement API orqali qoldiq va `created_by` |
| `apps/configurator/tests/test_configuration.py` | `CFG-` raqami, omborda bor/yo'q (`stock` / `purchase`), umumiy narx, ACT'siz `finalize` bo'lmasligi, buyurtmaga biriktirish, Excel eksport, ACT faqat adminga |
| `apps/sales/tests/test_contract_flow.py` | `SHT-` raqami, 30% va 15% foizlar, qo'lda foiz, to'liq approve zanjiri, bugalter admin bosqichini o'tolmasligi, sales tasdiqlay olmasligi, to'lov sanoqni boshlashi va kassaga tushishi, timeline ranglari, narx bugalterdan yashirilishi |
| `apps/purchases/tests/test_purchase_flow.py` | `KIR-` raqami, bojxona+soliq bilan jami, `expected_at` hisoblanishi, `receive` ombor va kassaga ta'siri, takroriy `receive` xatosi, yo'ldagilar ro'yxati, sales kirim qo'sha olmasligi |
| `apps/finance/tests/test_kassa.py` | tizim kategoriyalari, yo'nalish kategoriyadan olinishi, `summary` balansi, yangi yacheyka qo'shish, qarz kirimi va deadline, qarz yopilishi, xarajat so'rovi admin ruxsati bilan, rad etish |
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
