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

Hozirgi holat: **433 ta test, hammasi OK**.

---

## Qamrov

| Fayl | Nimani tekshiradi |
|---|---|
| `apps/accounts/tests/test_user_api.py` | rol propertylari, default rol `sales`, `/users/me/`, foydalanuvchilar ro'yxati faqat adminga, parol bilan yaratish |
| `apps/core/tests/test_seed_demo.py` | seed_demo: modul bo'yicha sonlar, configuratordan ochilgan TLD va uch tomonga xabar, engineer qo'shgan yangi tovar (WIFI-6E), faol shartnomada 2 ta to'lov, shartnoma bosqichlari to'liq qamrovi, faol shartnoma qizil zonada, kirim turlari, haqiqiy jarayondan o'tgan ta'minotchi qarzi (5 mln), yetishmayotgan mahsulot misollari, kassa musbat, idempotentlik, dashboard boyligi |
| `apps/core/tests/test_company_profile.py` | Bajaruvchi rekvizitlari: birinchi GET bo'sh yozuv ochishi, admin to'ldirib hamma o'qishi, sales/bugalter yozsa 403, singleton (ikkinchi yozuv bloklanadi), PATCH yagona yozuvni tahrirlashi |
| `apps/core/tests/test_docs_consistency.py` | Hujjatlar kod bilan mos turishi: har bir endpoint 05-API.md da, har bir permission sinfi 03-ROLES da yozilgani, o'chirilgan nomlar qolmagani, README dagi endpoint soni haqiqiy songa mosligi |
| `apps/accounts/tests/test_role_matrix.py` | TZ 8: 4 rol × 15 bo'lim o'qish matritsasi va 11 bo'lim yozish matritsasi; sales uchun kassa/kirim/to'ldirish yopiqligi va ombor faqat o'qish uchun ekani |
| `apps/accounts/tests/test_jwt_auth.py` (`DemoUsersLoginTests`) | 4 rolning har biri JWT bilan kirishi, `/users/me/` dan o'z rolini olishi, login'dan keyin rol bo'yicha ruxsatlar (audit faqat adminga, replenishments buyurtmachiga, kassa bugalterga) |
| `apps/accounts/tests/test_jwt_auth.py` | login throttle (31-urinish 429), login token juftligini qaytarishi, noto'g'ri parol 401, access token bilan himoyalangan endpoint ochilishi, refresh rotatsiyasi, token muddatlari sozlamadan |
| `apps/clients/tests/test_client_api.py` | jismoniy shaxs uchun passport/JSHSHIR majburiyligi, yuridik uchun INN/manzil, telefon unique, bugalter client qo'sha olmasligi |
| `apps/inventory/tests/test_seed_stock.py` | seed_stock: bo'sh/kam mahsulot maqsad darajaga to'ladi (reorder_level*2 yoki 10), yetarlisiga tegilmaydi, idempotent |
| `apps/inventory/tests/test_product_kinds.py` | Ikki xil kirim: product_kind bilan tayyor model/butlovchi yaratilishi, noto'g'ri tur 400; tarkib (product-specs) yozish engineer'da, yangi butlovchi nomi bilan, butlovchiga tarkib 400, takror 400, buyurtmachiga 403, tahrir/o'chirish |
| `apps/inventory/tests/test_single_warehouse.py` | Bitta ombor qoidasi: ikkinchi ombor bloklanadi, mavjudini tahrirlash mumkin, `main_warehouse()` yagona omborni qaytaradi va bo'sh tizimda o'zi ochadi |
| `apps/inventory/tests/test_stock_services.py` | `in` qoldiqni oshirishi, `out` kamaytirishi, `adjust` yakuniy qoldiqni qo'yishi, `is_low_stock`, movement API orqali qoldiq va `created_by` |
| `apps/configurator/tests/test_configuration.py` | `CFG-` raqami, omborda bor/yo'q (`stock` / `purchase`), umumiy narx, ACT'siz `finalize` bo'lmasligi, buyurtmaga biriktirish, Excel eksport, ACT sales bosqichida (engineer'ga 403) |
| `apps/sales/tests/test_contract_flow.py` | `SHT-` raqami, 30% va 15% foizlar, qo'lda foiz, to'liq approve zanjiri, bugalter admin bosqichini o'tolmasligi, sales tasdiqlay olmasligi, to'lov sanoqni boshlashi va kassaga tushishi, qo'shimcha to'lov /contract-payments/ orqali (paid_at'siz, kassa bilan, completed), draft'ga to'lov 400, configuration filtri, timeline ranglari, narx bugalterdan yashirilishi |
| `apps/purchases/tests/test_purchase_flow.py` | `KIR-` raqami, bojxona+soliq bilan jami, `expected_at` hisoblanishi, `receive` ombor va kassaga ta'siri, takroriy `receive` xatosi, yo'ldagilar ro'yxati, sales kirim qo'sha olmasligi, exe va 10 MB+ fayl rad etilishi |
| `apps/finance/tests/test_kassa.py` | tizim kategoriyalari, yo'nalish kategoriyadan olinishi, `summary` balansi, yangi yacheyka qo'shish, qarz kirimi va deadline, qarz yopilishi, xarajat so'rovi admin ruxsati bilan, rad etish |
| `apps/sales/tests/test_contract_print.py` | Finalize'da avtomatik draft shartnoma (ZVK mijozi yoki tanadagi mijoz bilan, QQS bilan jami, mijozsiz contract=null, noto'g'ri mijoz 400) va chop etish shakli: kompaniya+mijoz rekvizitlari, qatorlar/yig'indilar, bugalterga 403, adminga 200 |
| `apps/sales/tests/test_vat.py` | Shartnomada QQS: default 12% (5 mln + 600 ming = 5,6 mln), jami QQS bilan sinxronlanishi va oldindan to'lov, 0% imtiyoz, QQS maydonlari bugalterdan yashirinligi |
| `apps/procurement/tests/test_sales_gate.py` | Sales-gate: konfiguratsiyali hisob submit'da sales'ga borishi va notification, oddiy to'ldirish bugalterga, sales'siz bugalter tasdiqlay olmasligi (403), to'liq sales→bugalter→admin zanjiri va tarixda sales bosqichi, mijoz rad etsa buyurtmachiga qaytishi, sales hisobni o'qiy olishi |
| `apps/procurement/tests/test_vat.py` | To'ldirishda QQS: default 0, buyurtmachi 12% kiritganda yig'indilar, total_amount = QQS bilan qatorlar + logistika + boshqa |
| `apps/procurement/tests/test_replenishment_flow.py` | TZ 7: yetishmayotganlar ro'yxati, hisob shakllantirish, narxsiz yuborishning bloklanishi, buyurtmachi→bugalter→admin zanjiri, pul yetmasa qarzga o'tishi (1 400 000 / 500 000 / 900 000), qarz muddati kirimdan 60 kun, ombor qoldig'i, bojxona bosqichi, admin qatorni tahrirlashi |
| `apps/configurator/tests/test_variant_pricing.py` | TZ 6.2: narx ombordan olinishi, narxsiz qatorning bloklanishi, variant yaratilishi, bir xil tarkibning qayta ishlatilishi, tayyor variant narxi |
| `apps/configurator/tests/test_configuration_request.py` | Sales→Engineer zayavka oqimi: ZVK raqami, take/complete faqat engineerga, take'da konfiguratsiya avtomatik ochilishi, sales'ga notification, configuratsiz complete 400 |
| `apps/sales/tests/test_contract_flow.py` (yangilandi) | #2: to'lov mol chiqarmaydi, ship chiqaradi va yopadi, stok yetmasa to'lov o'tadi/ship kutadi, to'lovsiz ship 400, shartnomadan TLD zanjiri (contract FK, owner_sales, bitta ochiq TLD, receive -> bron -> ship) |
| `apps/configurator/tests/test_quantity.py` | #3 partiya: zayavkadan ko'chishi, shortage ×partiya, yumshoq bron ×partiya, assemble butun partiyani yasashi (qisman yo'q — 400), avto-shartnomada miqdor va QQS'li jami, modify'da partiya harakatlari |
| `apps/configurator/tests/test_required_from_stock.py` | 3-to'plam §1: modify bronlari faqat model+qo'shilganlar, missing'da bazaviy model, TLD da model qatori, kirimdan keyin assemble o'tishi, o'zgarmagan qator yetishmovchilikka tushmasligi, build o'zgarmagani |
| `apps/configurator/tests/test_change_quantity.py` | 4-to'plam §2: approved'da son/bron/zayavka birga o'zgarib pending_sales'ga qaytishi, yig'ilganda 400, chernovikdan o'tgan TLD da 400 (raqami bilan), chernovik TLD to'smasligi, sales 403, noto'g'ri son 400 |
| `apps/configurator/tests/test_contract_first.py` | YANGI OQIM 1-bosqich: approve'da draft SHT ochilishi (egasi zayavka sales'i, qator base×partiya), mijozsiz 400, qayta tasdiqda dublikat yo'q, narxsiz submit 400 + request-prices oqimi (buyurtmachi narx kiritadi, sales xabar oladi), SHT ready'gacha bron qo'ymasligi, to'lovda CFG bronining HARD/muddatsiz bo'lishi, §6-B ustama |
| `apps/configurator/tests/test_payment_gates.py` | YANGI OQIM 2-bosqich: to'lovgacha assemble/ta'minot 400 (SHT raqami bilan), rad etilganda boshqa matn, to'lovdan keyin o'tishi, B13 (partiya/shartnoma/qatorlar quli — admin ham), draft SHT songa ergashishi, B16 (ZVK miqdori sinxron va holat quli) |
| `apps/configurator/tests/test_request_loop.py` | B15: izohsiz reject 400, returned faqat sales'da (hovuzdan chiqadi), in_progress'da CFG bekor + bron bo'shashi, resend hovuzga qaytarishi (begona sales 404), events tarixi |
| `apps/configurator/tests/test_cancel_chain.py` | B12/B17: zayavkadan butun zanjir yopilishi (SHT/CFG/ZVK/bron), to'lovdan keyin 400, sabab majburiy, faqat egasi/admin, to'langan TLD ochiq qolib ogohlantirish qaytishi |
| `apps/sales/tests/test_payment_limit.py` | 4-to'plam §3: qoldiqdan katta to'lov 400 (kassaga yozilmaydi), aynan qoldiq o'tib yopilishi, nol/manfiy 400, /contract-payments/ ham rad etishi, manfiy balansda 400 (500 emas) |
| `apps/sales/tests/test_didox_steps.py` | B3/B14: send-didox raqam majburiy va pending_didox'ga o'tishi, confirm-didox -> admin/chegara skip, pending_didox'dan orqaga yo'l yo'qligi, eski bitta qadamli approve mosligi, foiz faqat qoralamada o'zgarishi |
| `apps/core/tests/test_resync_reservations.py` | 4-to'plam §1: eski xato bron (mashina ichidagi qism) yangi ta'rifga qayta qurilishi, terminal hujjat broni bo'shatilib qayta yozilmasligi |
| `apps/core/tests/test_roadmap.py` | B8/B11: uch kirish nuqtasidan bir xil roadmap (barcha rollar, 200), 18 qadam holatlari (done/current/blocked), javobda pul yo'qligi, can_open matritsasi, repeats, cancelled belgisi; migrate_to_contract_first (dry-run, mijozsiz ro'yxat, SHT ochilishi) |
| `apps/core/tests/test_notifications_cleanup.py` | 4-to'plam §4: mark-all-read faqat o'zinikini yopib son qaytarishi (takrori 0), object_id filtri, tasdiqda bajargan odamning eslatmasi yopilib boshqaniki turishi, resolve idempotentligi |
| `apps/configurator/tests/test_approval_flow.py` | #4: sales navbatida configuration_review, ta'minot tasdiqqacha 400, receive'da engineerga 'mol keldi', assemble'da act_suggestion, pending_sales'da tahrir qulfi |
| `apps/finance/tests/test_supplier_debt_cash.py` | TOPSHIRIQ-2 #1: qarzli to'lovda kassada faqat bitta chiqim (fantom kirim yo'q, qoldiq aynan naqd qismga kamayadi), qarz yopilgach jami chiqim = hisob summasi, shaxsiy qarz kirim yozadi, ta'minotchi qarzi yozmaydi |
| `apps/core/tests/test_sla.py` | TOPSHIRIQ #3: sla_deadline misollari (kesim 16:00, hafta oxiri o'tkaziladi), status_changed_at faqat holat o'zgarganda, turib qolgan ish egasida danger+waiting_days, adminda stale qator holder bilan, sidebar==my-work |
| `apps/procurement/tests/test_admin_threshold.py` | TOPSHIRIQ #2: kichik TLD adminsiz (avtomatik tarix yozuvi, xabar 'Admin tasdiqladi' demaydi), katta/valyuta/0 — adminga, shartnoma chegarasi TLD ga ta'sir qilmaydi |
| `apps/core/tests/test_ownership.py` | EGALIK §3 egalik: sales boshqaning shartnomasini ko'rmaydi/tahrirlamaydi/yubormaydi (404), bugalter/admin hammasini ko'radi, engineer o'z konfiguratsiyasi + new zayavkalar, sales o'z zayavkasidan tug'ilgan konfiguratsiyani ko'radi, sales faqat o'z pending_sales hisobini ko'radi, admin sales nomidan yubora oladi |
| `apps/core/tests/test_my_work.py` | EGALIK §2/§5: my-work rol bo'yicha (sales o'ziniki, bugalter/admin navbati, engineer new+o'ziniki, buyurtmachi + low_stock, pending_sales faqat egasiga), sidebar == my-work counts; created_by_name (to'liq ism), created_by filtri, users o'qish bugalterga/yozish yo'q |
| `apps/core/tests/test_notification_targeting.py` | Bildirishnoma manzillari (EGALIK §4): shartnoma muddati — egasi+bugalter+admin, qarz — bugalter+admin, kirim — bugalter+buyurtmachi, user=null yo'q, per-user idempotent; request-procurement/mijoz roziligi — faqat zayavka egasi |
| `apps/inventory/tests/test_product_pricing.py` | §10.2: PATCH narx siyosati (bugalter 200, sales 403), identifikatsiya maydonlari read-only, POST 405 |
| `apps/inventory/tests/test_reservations.py` | §11.4 bron: qattiq/yumshoq, qisman band, ikkinchi shartnoma faqat erkinni oladi, reject bo'shatadi, to'lov shipped qiladi, o'z broni o'zini to'smaydi, release faqat admin+sabab, muddat o'tishi va qayta bron |
| `apps/sales/tests/test_contract_lock_and_sync.py` | §10.3: qator o'zgarishida total sinxron, submit'dan keyin qulf (admin istisno), rejected tahrir + qayta submit |
| `apps/sales/tests/test_didox_and_threshold.py` | §11.2 Didox raqami/sanasi, payment qadami tarixda; §11.3 chegara: kichik — admin chetlab, katta/valyuta/0 — adminga |
| `apps/sales/tests/test_chain_closure.py` | §10.8: Lead avtomatik bog'lanadi, ZVK arxiv, CFG sold |
| `apps/procurement/tests/test_pay_freeze_and_kir.py` | §10.5 muzlatish, §10.9 kassa FK+yacheyka, §10.10 yo'naltirilgan xabar, §10.4 kassa sizmasligi, §4.3 avto-KIR va qayta receive taqiqi |
| `apps/purchases/tests/test_status_guard.py` | §10.6: received→draft 400, PATCH bilan received 400, faqat oldinga |
| `apps/core/tests/test_dashboard_roles.py` | §10.4: kassa bloki sales/buyurtmachi/engineerga null |
| `apps/finance/tests/test_expense_direction.py` | §10.12.1: kirim yacheykasiga xarajat so'rovi 400 |
| `apps/procurement/tests/test_receive_cost_price.py` | receive'da xarid narxi katalogga tushishi (cost_price/stock_price), 0 narx mavjud tannarxni buzmasligi, bog'langan konfiguratsiya qatori narx olib needs_price'dan chiqishi |
| `apps/procurement/tests/test_pay_parsing.py` | pay: `debt_amount` satr bo'lsa ham 200 (prod'da 500 berardi), bo'sh satr — avtomatik shortfall, noto'g'ri format — 400 |
| `apps/sales/tests/test_payment_parsing.py` | confirm-payment: `amount` satr — 200, noto'g'ri format — 400 (500 emas) |
| `apps/procurement/tests/test_chain_notifications.py` | TLD tasdiq zanjirida bildirishnomalar: oddiy submit'da bugalterga, sales tasdig'ida bugalterga, bugalter tasdig'ida **adminga** (tuzatilgan xato), admin tasdig'ida bugalterga (to'lov) va buyurtmachiga |
| `apps/sales/tests/test_contract_notifications.py` | Shartnoma zanjirida bildirishnomalar: submit'da bugalterga, bugalter tasdig'ida adminga, admin tasdig'ida bugalter+sales'ga, reject'da sales'ga (izoh bilan) |
| `apps/configurator/tests/test_procurement_flag.py` | Konfiguratsiyada buyurtmachi flagi: yuborilmaganda `procurement=null`, yuborilgach TLD raqami/holati va `sent_to_procurement=true`, takror yuborish 400, bekor qilingan hisob flagni bo'shatadi, rad etilgani ochiq qoladi, kirim qilingani yopadi, ro'yxatda ham chiqadi |
| `apps/configurator/tests/test_missing_to_procurement.py` | Engineer bazada yo'q tovarni configuratordan qo'shishi (`new_component_name`, takror nom yaratilmasligi), request-procurement: yetishmaganlardan TLD ochilishi, buyurtmachi/sales/bugalterga xabar, hammasi omborda bo'lsa 400, sales'ga 403, zanjir buyurtmachi submit'iga ulanishi |
| `apps/configurator/tests/test_front_fixes.py` | Front topgan xatolar regressiyasi: configuration-items'da `configuration` maydoni (400, 500 emas), engineer notificationlari, `configuration` filtri, ready/attached qulfi, take'da zavod tarkibi va tana ustuvorligi, komponent bazaviy bo'la olmasligi, sales finalize tanadagi ACT bilan (engineer'ga 403), sales ACT yarata olishi |
| `apps/finance/tests/test_kassa.py` (`LoanRepaidBugTests`) | Qarz bug'i regressiyasi: yangi qarzda repaid=0, qisman/to'liq qaytarish, ortiqcha to'lov va yopiq qarzga 400 |
| `apps/core/tests/test_dashboard_and_audit.py` | dashboard bo'limlari va balans, `ActivityLog` yozilishi, audit faqat adminga, `check_deadlines` eslatmalari va idempotentligi, kelishuv aloqa eslatmasi (bugun/ertaga sariq, o'tgan sana qizil, salesga shaxsan; sanasiz/yopiqlarga yozilmasligi), notification `mark-read` |

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
