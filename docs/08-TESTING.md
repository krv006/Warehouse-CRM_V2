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

Hozirgi holat: **584 ta test, hammasi OK**.

---

## Qamrov

| Fayl | Nimani tekshiradi |
|---|---|
| `apps/accounts/tests/test_user_api.py` | rol propertylari, default rol `sales`, `/users/me/`, foydalanuvchilar ro'yxati faqat adminga, parol bilan yaratish |
| `apps/core/tests/test_seed_demo.py` | seed_demo: modul bo'yicha sonlar, configuratordan ochilgan TLD va uch tomonga xabar, engineer qo'shgan yangi tovar (WIFI-6E), faol shartnomada 2 ta to'lov, shartnoma bosqichlari to'liq qamrovi, faol shartnoma qizil zonada, kirim turlari, haqiqiy jarayondan o'tgan ta'minotchi qarzi (5 mln), yetishmayotgan mahsulot misollari, kassa musbat, idempotentlik, dashboard boyligi |
| `apps/core/tests/test_fix_stale_didox.py` | QOLGAN-ISHLAR #1: `fix_stale_didox` komandasi — SHT-00058 uslubidagi yozuvni `ready_for_didox`ga qaytarishi, `--dry-run` yozmasligi, haqiqiy (rad etilmagan) eski yozuvga tegmasligi |
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
| `apps/configurator/tests/test_change_quantity.py` | 4-to'plam §2: approved'da son/bron/zayavka birga o'zgarib pending_sales'ga qaytishi, yig'ilganda 400, chernovikdan o'tgan TLD da 400 (raqami bilan), chernovik TLD to'smasligi, engineer 403 (§4: sonni sales belgilaydi), noto'g'ri son 400 |
| `apps/configurator/tests/test_contract_first.py` | YANGI OQIM 1-bosqich: approve'da draft SHT ochilishi (egasi zayavka sales'i, qator base×partiya), mijozsiz 400, qayta tasdiqda dublikat yo'q, narxsiz submit 400 + request-prices oqimi (buyurtmachi narx kiritadi, sales xabar oladi), SHT ready'gacha bron qo'ymasligi, to'lovda CFG bronining HARD/muddatsiz bo'lishi, §6-B ustama |
| `apps/configurator/tests/test_payment_gates.py` | YANGI OQIM 2-bosqich: to'lovgacha assemble/ta'minot 400 (SHT raqami bilan), rad etilganda boshqa matn, to'lovdan keyin o'tishi, B13 (partiya/shartnoma/qatorlar quli — admin ham), draft SHT songa ergashishi, B16+§4 (ZVK miqdori sinxron; `done`da ham ochiq — sales ko'rigiga qaytadi; arxivda 400) |
| `apps/configurator/tests/test_request_loop.py` | B15/9-to'plam: izohsiz reject 400, returned faqat sales'da, in_progress'da reject 400 (ish tegilmaydi), release (hovuzga: CFG bekor+bron bo'sh, o'ziga xabar yo'q, keyingi take toza chernovik), ask-sales/answer (bron joyida, suhbat approvals'da, submit davom etadi), resend, events tarixi |
| `apps/configurator/tests/test_cancel_chain.py` | B12/B17: zayavkadan butun zanjir yopilishi (SHT/CFG/ZVK/bron), to'lovdan keyin 400, sabab majburiy, faqat egasi/admin, to'langan TLD ochiq qolib ogohlantirish qaytishi |
| `apps/sales/tests/test_payment_limit.py` | 4-to'plam §3: qoldiqdan katta to'lov 400 (kassaga yozilmaydi), aynan qoldiq o'tib yopilishi, nol/manfiy 400, /contract-payments/ ham rad etishi, manfiy balansda 400 (500 emas) |
| `apps/sales/tests/test_didox_steps.py` | 12-§1/B3/B14: admin tasdig'i Didoxdan OLDIN (pending_admin -> ready_for_didox), send-didox faqat ready_for_didox'dan va raqam majburiy, confirm-didox to'g'ridan approved, chegaradan past shartnoma adminsiz ready_for_didox'ga yetishi, pending_didox'dan orqaga yo'l yo'qligi, eski yozuv (Didoxi tasdiqlangan) to'g'ridan approved, QOLGAN-ISHLAR #1: rad etilib qayta boshlangan shartnomada ESKI Didox izi hisobga olinmasligi (SHT-00058), foiz faqat qoralamada o'zgarishi |
| `apps/core/tests/test_resync_reservations.py` | 4-to'plam §1: eski xato bron (mashina ichidagi qism) yangi ta'rifga qayta qurilishi, terminal hujjat broni bo'shatilib qayta yozilmasligi |
| `apps/core/tests/test_roadmap.py` | B8/B11: uch kirish nuqtasidan bir xil roadmap (barcha rollar, 200), 20 qadam holatlari (done/current/blocked), javobda pul yo'qligi, can_open matritsasi, repeats, cancelled belgisi, shartli qadamlar (§1–2: chernovikda current=submitted, narx so'ralganda current, missing bo'sh — skipped, TLD ochiq — chain current, chegara ostida admin skipped); migrate_to_contract_first (dry-run, mijozsiz ro'yxat, SHT ochilishi); QOLGAN-ISHLAR #3: finalize SLA yig'ilgan paytdan (CFG holatidan emas); QOLGAN-ISHLAR #6: procurement_sent/taken qadamlarida hujjat yo'q paytda ham havola borligi |
| `apps/core/tests/test_roadmap_list.py` | 7-to'plam §1: bugalter navbati kelgan zanjirni ko'rishi (egasi bo'lmasa ham), buyurtmachida bo'sh ro'yxat, engineer o'z zanjirlarini, detal bilan bir xil shakl (20 qadam, pul yo'q), muddatdan o'tgani birinchi + limit, state=closed/all; 10-§5: qo'l tekkizgan odam navbat o'tgach ham ko'rishi, engineer hovuzi olingach torayishi, TLD yo'ldaligida buyurtmachi hovuzi |
| `apps/sales/tests/test_delivered_by.py` | 10-§7/11-§3: sales (egasi) yetkazadi va `delivered_by` yoziladi, buyurtmachi endi 403, eski `delivered_by=buyurtmachi` yozuvda ko'rinish saqlanishi (begona buyurtmachiga 404), roadmap ship qadami ismi |
| `apps/core/tests/test_chain_tld.py` | 11-to'plam: konfiguratsiyali shartnomada request-procurement yopiq, CFG eshigi shartnoma tomoni TLD'sini ham ko'rishi, oddiy shartnomada eshik ishlashi; qoldiq to'lov qadami (bugalter roli, «Qoldiq to'lov» nomi, hovuzda ko'rinishi, yopilganda yana «Yakunlandi») |
| `apps/core/tests/test_chain_shapes.py` | 8-to'plam: qo'lda SHT zanjirida ZVK/CFG qadamlari skipped va joriy to'g'ri, ZVK'siz CFG'da faqat zayavka qadami skipped; bitta CFG'ga ikkinchi shartnoma 400 (bekor qilingani hisobga olinmaydi); cancel_reason ikkala yo'lda to'lishi va javobda ko'rinishi |
| `apps/core/tests/test_notifications_cleanup.py` | 4-to'plam §4: mark-all-read faqat o'zinikini yopib son qaytarishi (takrori 0), object_id filtri, tasdiqda bajargan odamning eslatmasi yopilib boshqaniki turishi, resolve idempotentligi |
| `apps/configurator/tests/test_approval_flow.py` | #4: sales navbatida configuration_review, ta'minot tasdiqqacha 400, receive'da engineerga 'mol keldi', assemble'da act_suggestion, pending_sales'da tahrir qulfi |
| `apps/finance/tests/test_supplier_debt_cash.py` | TOPSHIRIQ-2 #1: qarzli to'lovda kassada faqat bitta chiqim (fantom kirim yo'q, qoldiq aynan naqd qismga kamayadi), qarz yopilgach jami chiqim = hisob summasi, shaxsiy qarz kirim yozadi, ta'minotchi qarzi yozmaydi |
| `apps/core/tests/test_sla.py` | TOPSHIRIQ #3: sla_deadline misollari (kesim 16:00, hafta oxiri o'tkaziladi), status_changed_at faqat holat o'zgarganda, turib qolgan ish egasida danger+waiting_days, adminda stale qator holder bilan, sidebar==my-work |
| `apps/procurement/tests/test_admin_threshold.py` | TOPSHIRIQ #2: kichik TLD adminsiz (avtomatik tarix yozuvi, xabar 'Admin tasdiqladi' demaydi), katta/valyuta/0 — adminga, shartnoma chegarasi TLD ga ta'sir qilmaydi |
| `apps/core/tests/test_ownership.py` | EGALIK §3 egalik: sales boshqaning shartnomasini ko'rmaydi/tahrirlamaydi/yubormaydi (404), bugalter/admin hammasini ko'radi, engineer o'z konfiguratsiyasi + new zayavkalar, sales o'z zayavkasidan tug'ilgan konfiguratsiyani ko'radi, sales faqat o'z pending_sales hisobini ko'radi, admin sales nomidan yubora oladi |
| `apps/core/tests/test_my_work.py` | EGALIK §2/§5: my-work rol bo'yicha (sales o'ziniki, bugalter/admin navbati, engineer new+o'ziniki, buyurtmachi + low_stock, pending_sales faqat egasiga), sidebar == my-work counts; created_by_name (to'liq ism), created_by filtri, users o'qish bugalterga/yozish yo'q. QOLGAN-ISHLAR-2 §6: `needs_price` faqat buyurtmachiga. 19-§2: yetkazilgan-u qoldiq to'lanmagan `active` shartnoma bugalter navbatida (`awaiting_balance`), hali yetkazilmagani hamon sales'da (`ship_contract`) |
| `apps/core/tests/test_notification_targeting.py` | Bildirishnoma manzillari (EGALIK §4): shartnoma muddati — egasi+bugalter+admin, qarz — bugalter+admin, kirim — bugalter+buyurtmachi, user=null yo'q, per-user idempotent; request-procurement/mijoz roziligi — faqat zayavka egasi |
| `apps/inventory/tests/test_product_pricing.py` | §10.2: PATCH narx siyosati (bugalter 200, sales 403), identifikatsiya maydonlari read-only, POST 405 |
| `apps/inventory/tests/test_reservations.py` | §11.4 bron: qattiq/yumshoq, qisman band, ikkinchi shartnoma faqat erkinni oladi, reject bo'shatadi, to'lov shipped qiladi, o'z broni o'zini to'smaydi, release faqat admin+sabab, muddat o'tishi va qayta bron |
| `apps/sales/tests/test_contract_lock_and_sync.py` | §10.3: qator o'zgarishida total sinxron, submit'dan keyin qulf (admin istisno), rejected tahrir + qayta submit |
| `apps/sales/tests/test_didox_and_threshold.py` | 12-§1: bugalter tasdig'ida imzo sanasi to'lishi, Didox raqami endi send-didox'da saqlanishi, payment qadami tarixda; §11.3 chegara: kichik — admin chetlab ready_for_didox'ga, katta/valyuta/0 — adminga |
| `apps/sales/tests/test_chain_closure.py` | §10.8: Lead avtomatik bog'lanadi, ZVK arxiv, CFG sold |
| `apps/procurement/tests/test_pay_freeze_and_kir.py` | §10.5 muzlatish, §10.9 kassa FK+yacheyka, §10.10 yo'naltirilgan xabar, §10.4 kassa sizmasligi, §4.3 avto-KIR va qayta receive taqiqi |
| `apps/purchases/tests/test_status_guard.py` | §10.6: received→draft 400, PATCH bilan received 400, faqat oldinga |
| `apps/core/tests/test_dashboard_roles.py` | §10.4: kassa bloki sales/buyurtmachi/engineerga null |
| `apps/finance/tests/test_expense_direction.py` | §10.12.1: kirim yacheykasiga xarajat so'rovi 400 |
| `apps/procurement/tests/test_receive_cost_price.py` | receive'da xarid narxi katalogga tushishi (cost_price/stock_price), 0 narx mavjud tannarxni buzmasligi, bog'langan konfiguratsiya qatori narx olib needs_price'dan chiqishi |
| `apps/procurement/tests/test_pay_parsing.py` | pay: `debt_amount` satr bo'lsa ham 200 (prod'da 500 berardi), bo'sh satr — avtomatik shortfall, noto'g'ri format — 400 |
| `apps/sales/tests/test_payment_parsing.py` | confirm-payment: `amount` satr — 200, noto'g'ri format — 400 (500 emas) |
| `apps/procurement/tests/test_chain_notifications.py` | TLD tasdiq zanjirida bildirishnomalar: oddiy submit'da bugalterga, sales tasdig'ida bugalterga, bugalter tasdig'ida **adminga** (tuzatilgan xato), admin tasdig'ida bugalterga (to'lov) va buyurtmachiga |
| `apps/sales/tests/test_contract_notifications.py` | Shartnoma zanjirida bildirishnomalar: submit'da bugalterga, bugalter tasdig'ida adminga, admin tasdig'ida (12-§1) bugalterga "Didoxga yuboring" + sales'ga, Didox tasdiqlangach (endi shu yerda) bugalterga "pul kutilmoqda", reject'da sales'ga (izoh bilan) |
| `apps/configurator/tests/test_multi_model_contract.py` | 12-§2 (C): ikkinchi model mavjud qoralamaga qo'shiladi (yangi shartnoma ochilmaydi), draft bo'lmagan/boshqa mijoz/boshqa egadagi shartnomaga qo'shib bo'lmasligi, `active_contract` qator orqali topilishi, bir modelning TLD'si ikkinchisini bloklamasligi, yopilganda ikkala zayavka ham arxivlanishi |
| `apps/sales/tests/test_contract_document.py` | 13-§1: GET lazily hujjat ochadi, engineer/buyurtmachiga yopiq, sales egasi/admin o'qiydi-tahrirlamaydi, egasiz sales 404, bugalter har saqlashda yangi versiya, Didoxdan keyin tahrir yopiq, o'rin egallovchilar ko'rsatishda to'ladi va jami summa hujjatga kirgan hammaga ko'rinishi (QOLGAN-ISHLAR #3), `body_raw` render qilinmagan holda qaytishi (#2), `.docx` bo'lmagan fayl 400, `.docx` yuklanganda mammoth orqali HTML'ga o'girilib asl fayl saqlanishi; 15-§3: `source_file`/`source_file_name`/`source_uploaded_at` GET javobida, yuklanmagunicha `null`; **`CollaboraWopiTests`** (15-§A): shablon `{{ }}` yuklashda statik to'lishi, `edit-session` faqat bugalterda va `.docx` talab qilishi, WOPI `CheckFileInfo` token bilan/tokensiz, `GetFile` xom baytlarni qaytarishi, `LOCK`/`UNLOCK` qulf ziddiyati (409 + `X-WOPI-Lock`), `PutFile` versiyani oshirib yangi `ContractDocumentVersion` yozishi, begona qulfda 409; 20-§1: admin ham `can_edit`/yuklash/`edit-session`da bugalter bilan bir xil (Didoxdan keyin ikkalasi ham yopiq), sales/engineer/buyurtmachiga hamon yopiq |
| `apps/configurator/tests/test_request_lines.py` | 12-§2 (B): aralash zayavka (model + tovar qatori) yaratilishi, bitta zayavkada modelli qator uchun avtomatik chernovik, tovar turida noto'g'ri mahsulot turi rad etilishi, tovar qatori shartnoma ochilganda avtomatik ContractItem bo'lishi, barcha qator tugagunicha zayavka DONE bo'lmasligi, hovuzga qaytarishda barcha chernoviklar bekor bo'lishi, bitta modelli (oddiy) zayavka regressiyasi |
| `apps/configurator/tests/test_procurement_flag.py` | Konfiguratsiyada buyurtmachi flagi: yuborilmaganda `procurement=null`, yuborilgach TLD raqami/holati va `sent_to_procurement=true`, takror yuborish 400, bekor qilingan hisob flagni bo'shatadi, rad etilgani ochiq qoladi, kirim qilingani yopadi, ro'yxatda ham chiqadi |
| `apps/configurator/tests/test_missing_to_procurement.py` | Engineer bazada yo'q tovarni configuratordan qo'shishi (`new_component_name`, takror nom yaratilmasligi), request-procurement: yetishmaganlardan TLD ochilishi, buyurtmachi/sales/bugalterga xabar, hammasi omborda bo'lsa 400, sales'ga 403, zanjir buyurtmachi submit'iga ulanishi |
| `apps/configurator/tests/test_front_fixes.py` | Front topgan xatolar regressiyasi: configuration-items'da `configuration` maydoni (400, 500 emas), engineer notificationlari, `configuration` filtri, ready/attached qulfi, take'da zavod tarkibi va tana ustuvorligi, komponent bazaviy bo'la olmasligi, sales finalize tanadagi ACT bilan (engineer'ga 403), sales ACT yarata olishi |
| `apps/finance/tests/test_kassa.py` (`LoanRepaidBugTests`) | Qarz bug'i regressiyasi: yangi qarzda repaid=0, qisman/to'liq qaytarish, ortiqcha to'lov va yopiq qarzga 400 |
| `apps/core/tests/test_dashboard_and_audit.py` | dashboard bo'limlari va balans, `ActivityLog` yozilishi, audit faqat adminga, `check_deadlines` eslatmalari va idempotentligi, kelishuv aloqa eslatmasi (bugun/ertaga sariq, o'tgan sana qizil, salesga shaxsan; sanasiz/yopiqlarga yozilmasligi), notification `mark-read` |
| `apps/configurator/tests/test_deal.py` | 14-to'plam "bitta zayavka — bitta savdo": bitta modelli zanjirda `deal: null` regressiyasi, ko'p modelli `deal` bloki shakli, ikkinchi model `contract` bermasdan mavjud qoralamaga qo'shilishi (`separate_contract` bilan yangisi, yuborilgan shartnomaga urinishda tushunarli 400), tugamagan model bo'lsa shartnoma yuborish bloklanishi (`pending_models`), `detach` (cancel/separate, to'langanida 400), roadmap qadamlarining eng orqada qolgan model bo'yicha kutishi, ko'p modelli savdoda BITTA TLD (qo'shilishi, `pending_admin`da yangisiga ruxsat, bitta modelli zanjir tegilmasligi), `finalize`da sibling ACT qayta ishlatilishi va savdo darajasidagi ACT matni |
| `apps/configurator/tests/test_deal_actions.py` | 16-to'plam: bitta modelli ZVKda savdo `submit` = model `submit` (A1); ikki modelli — bittasi tayyor emas bo'lsa `submit` 400 va hech biri o'zgarmasligi, `approve` ikkalasini ham tasdiqlab BITTA shartnoma ochishi, `assemble` qisman muvaffaqiyat (`assembled`/`pending`), `finalize` ikkalasini `ready` qilib BITTA ACT biriktirishi (A2); `ask-sales`/`answer` savdodagi barcha modelni bitta suhbat bilan ko'chirishi, `approvals` ikkala model sahifasida bir xil ko'rinishi (A3); `lines/` bilan `in_progress` zayavkaga model qo'shilganda CFG darhol ochilishi, `new`da ochilmasligi, bitta modelli ZVKni `deal`ga aylantirishi, shartnoma `pending_bugalter`da bloklanishi (B2/B3/B5g); `detach` — asosiy model chiqsa eng eski tirik model ko'tarilishi (qatori eski asosiyga qayta yo'naltiriladi — QOLGAN-ISHLAR-2 §5), yagona tirik modelda 400, yig'ilgan model ogohlantirishi, TLD `draft`da o'chishi va `pending_admin`da qolib ogohlantirishi (B5 a/b/c) |
| `apps/configurator/tests/test_deal_procurement_view.py` | 18-to'plam: TLD savdoda bitta, lekin javobda ikkita bo'lib ko'rinardi — ikki modelli savdoda `deal.models[*].missing` to'la kelishi (bekor qilinganda bo'sh), bitta modelli ZVKda `deal` null va `missing` o'zgarmasligi (§1); model A dan TLD ochilsa model B javobida ham `procurement`/`sent_to_procurement` to'la bo'lishi va `opened_for` to'g'ri ko'rsatishi, ikkinchi marta bosilsa takror hisob ochilmasligi, bitta modelli zanjirda `procurement` bugungidek ishlashi (§2) |
| `apps/configurator/tests/test_missing_assembled_guard.py` | 19-§1: yig'ilgan model to'ldirish hisobiga kirmasligi — `missing_items` yig'ilgandan keyin ham nolga tushmasa-da, `request-procurement` "Yig'ilmagan model yo'q" bilan 400 qaytarishi va yangi TLD ochilmasligi; ombor yetarli bo'lgan (yig'ilmagan) holatda eski xabar saqlanishi |
| `apps/sales/tests/test_contract_reject_target.py` | 20-§2: `reject_contract` ikki manzil — admin `pending_admin`dan `target=bugalter` bersa holat `pending_bugalter`ga o'tishi va bugalterga eslatma ketishi, `target=sales`/berilmagan holatda bugungidek `rejected` bo'lishi (regressiya); bugalter `target=bugalter` bosolmasligi (403); admin `pending_bugalter`dan `target=bugalter` bersa "allaqachon bugalterda" (400); noma'lum `target` 400; bugalterga qaytgach `approve` yana `pending_admin`ga borishi; yo'l xaritasidagi `contract_submitted.repeats` admin→bugalter qaytarishlarini sanamasligi; bron `pending_bugalter`da turib qolishi |
| `apps/configurator/tests/test_act_approval.py` | 20-§3: bitta model finalize qilinganda ACT `pending_bugalter`ga o'tishi va bugalter navbatida/eslatmasida ko'rinishi; ikki modelli savdoda BIRINCHI model finalize bo'lganda ACT hali `draft` qolishi, IKKINCHISI ham finalize bo'lgach `pending_bugalter`ga o'tishi; begona `approved` ACT finalize'da rad etilishi; engineer `approve` bosolmasligi, bugalter izohsiz `reject` qila olmasligi, rad etib-tuzatib-qayta yuborib-tasdiqlash aylanasi; yo'l xaritasida 20 qadam va joriy qadam `act_review` bo'lishi, konfiguratsiyasiz shartnomada bu qadam `skipped` bo'lishi |
| `apps/sales/tests/test_act_ship_guard.py` | 20-§3.4: ACT `pending_bugalter`/`rejected` bo'lsa `ship` 400 va mol chiqmasligi, `approved` bo'lsa `200` va yetkazilishi, `Contract.acts_approved` maydoni holatni to'g'ri ko'rsatishi, konfiguratsiyasiz (tayyor tovar) shartnomada `ship` bloklanmasligi (regressiya) |

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
