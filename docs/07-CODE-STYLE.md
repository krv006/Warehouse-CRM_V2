# 07 — Kod yozish qoidalari

Bu qoidalar **majburiy**. Yangi kod shu uslubda yozilmasa, loyihaga qo'shilmaydi.

---

## 1. Papka tuzilishi

```
apps/
    urls.py            # barcha app urls.py larini yig'adi
apps/<app>/
    __init__.py
    apps.py
    admin.py
    permissions.py     # kerak bo'lsa
    serializers.py
    services.py        # biznes logika
    urls.py            # shu ilovaning marshrutlari (path, router yo'q)
    views.py
    models/            # papka — models.py EMAS
        __init__.py    # barcha modellarni re-export qiladi
        <model>.py     # har bir model alohida faylda
    tests/             # papka — tests.py EMAS
        __init__.py
        test_<nima>.py
    migrations/
```

`models/__init__.py` namunasi:

```python
from apps.inventory.models.category import Category
from apps.inventory.models.warehouse import Warehouse
from apps.inventory.models.product import Product

__all__ = ['Category', 'Warehouse', 'Product']
```

Boshqa joydan import doim paketdan qilinadi:

```python
from apps.inventory.models import Product      # TO'G'RI
from apps.inventory.models.product import Product   # faqat models/ ichida
```

---

## 2. Import uslubi — prefikssiz

```python
# TO'G'RI
from django.db.models import CharField, DecimalField, ForeignKey, PROTECT

class Product(TimeStampedModel):
    name = CharField(max_length=200)
    sale_price = DecimalField(max_digits=18, decimal_places=2, default=0)
```

```python
# NOTO'G'RI
from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=200)
```

Xuddi shu qoida hamma joyda:

| Fayl | To'g'ri |
|---|---|
| `models/` | `from django.db.models import CharField, ForeignKey, CASCADE` |
| `serializers.py` | `from rest_framework.serializers import ModelSerializer, ReadOnlyField` |
| `views.py` | `from rest_framework.response import Response` |
| `admin.py` | `from django.contrib.admin import ModelAdmin, TabularInline, register` |

---

## 3. ForeignKey — aniq "app.Model" satri

```python
category = ForeignKey('inventory.Category', PROTECT, related_name='products')
created_by = ForeignKey('accounts.User', SET_NULL, related_name='orders', null=True, blank=True)
```

Qoidalar:

1. Birinchi argument — **doim** `'<app_label>.<ModelName>'` satri (klass obyekti emas).
2. `on_delete` — **pozitsion** argument, qavssiz: `CASCADE`, `PROTECT`, `SET_NULL`.
3. `related_name` — **har doim** ko'rsatiladi.
4. `SET_NULL` ishlatilsa `null=True, blank=True` ham bo'ladi.

Qaysi `on_delete`?

| Vaziyat | Tanlov |
|---|---|
| Qator o'z egasisiz mavjud bo'la olmaydi (`OrderItem` → `Order`) | `CASCADE` |
| Ma'lumotnoma o'chib ketmasligi kerak (`Product` → `Category`) | `PROTECT` |
| Foydalanuvchi / ixtiyoriy bog'lanish | `SET_NULL` |

---

## 4. Model qoidalari

```python
class Purchase(TimeStampedModel):
    """Kirim hujjati: O'zbekiston ichidan, import yoki ustav orqali."""

    class Type(TextChoices):
        LOCAL = 'local', "O'zbekiston ichidan"
        IMPORT = 'import', 'Import'

    number = CharField(max_length=30, unique=True, blank=True)

    def __str__(self):
        return f'{self.number} — {self.get_type_display()}'
```

- `TimeStampedModel` dan meros (`User` bundan mustasno).
- Tanlovlar — model ichidagi `TextChoices` klassi (`Type`, `Status`, `Kind`, `Method`, ...).
- O'zbekcha docstring va `__str__` — har bir modelda.
- Hisob-kitob `@property` orqali (`subtotal`, `total_amount`, `days_left`, `color`).
- Hujjat raqami `apps.core.utils.next_number(Model, 'PREFIX')` bilan `save()` ichida.

---

## 5. Serializer qoidalari

```python
class ProductSerializer(ModelSerializer):
    category_name = ReadOnlyField(source='category.name')
    unit_display = ReadOnlyField(source='get_unit_display')
    total_stock = ReadOnlyField()

    class Meta:
        model = Product
        fields = ['id', 'sku', 'name', 'category', 'category_name', 'unit', 'unit_display', 'total_stock']
```

- `get_x_display` va `..._name` maydonlari `ReadOnlyField` bilan.
- Nested qatorlar (`items`) `create()` va `update()` da qo'lda yoziladi.
- `created_by` doim `read_only_fields` da.

---

## 6. View qoidalari

```python
class PurchaseViewSet(BaseModelViewSet):
    """Kirim: O'zbekiston ichidan, import va ustav."""

    queryset = Purchase.objects.select_related('warehouse').prefetch_related('items__product').all()
    serializer_class = PurchaseSerializer
    permission_classes = [IsAdminOrBugalter]
    search_fields = ['number', 'supplier']
    filterset_fields = ['type', 'status']

    def receive(self, request, pk=None):
        """POST /purchases/{id}/receive/ — omborga kirim, kassaga chiqim."""
        purchase = receive_purchase(self.get_object(), request.user)
        self.log_action(ActivityLog.Action.UPDATE, purchase, 'Kirim qabul qilindi')
        return Response(self.get_serializer(purchase).data)
```

- `BaseModelViewSet` dan meros — `created_by` va `ActivityLog` avtomatik.
- Maxsus amallar oddiy metod (`@action` yo'q), manzili `urls.py` da yoziladi;
  metod docstring'ida qaysi endpoint ekani ko'rsatiladi.
- `queryset` da doim `select_related` / `prefetch_related` (N+1 bo'lmasin).
- `search_fields`, `filterset_fields`, `ordering_fields` — deklarativ.
- Ko'p bosqichli logika **view'da emas**, `services.py` da (`@atomic` bilan).

---

## 6.1 Marshrut qoidalari

**Router ishlatilmaydi.** Har bir ilovaning o'z `urls.py` fayli bo'ladi va har bir manzil
`path()` bilan aniq yoziladi:

```python
"""inventory marshrutlari: ombor bo'limi."""

from django.urls import path

from apps.core.routing import DETAIL, LIST
from apps.inventory.views import ProductViewSet, StockViewSet

urlpatterns = [
    path('products/', ProductViewSet.as_view(LIST), name='product-list'),
    path('products/<int:pk>/', ProductViewSet.as_view(DETAIL), name='product-detail'),

    path('stocks/', StockViewSet.as_view(LIST), name='stock-list'),
    path('stocks/<int:pk>/', StockViewSet.as_view(DETAIL), name='stock-detail'),
]
```

Nega router emas: router har bir ViewSet uchun keraksiz marshrutlarni ham yaratadi
(api-root, format-suffix, ishlatilmaydigan metodlar), URL jadvalini kattalashtiradi va
qaysi manzil qayerdan kelganini yashiradi. `path()` da hammasi ko'rinib turadi.

Takrorlanuvchi metod xaritalari — `apps/core/routing.py`:

| Nom | Qiymati |
|---|---|
| `LIST` | `{'get': 'list', 'post': 'create'}` |
| `DETAIL` | `{'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}` |
| `READ_LIST` | `{'get': 'list'}` |
| `READ_DETAIL` | `{'get': 'retrieve'}` |

Maxsus amallar — o'z manzili bilan, metod nomiga ulanadi:

```python
path('contracts/<int:pk>/confirm-payment/', ContractViewSet.as_view({
    'post': 'confirm_payment',
}), name='contract-confirm-payment'),
```

Qoidalar:

1. `@action` dekoratori **ishlatilmaydi** — u faqat routerga kerak. Amal oddiy metod bo'lib qoladi.
2. Amalga alohida ruxsat kerak bo'lsa, `get_permissions()` da `self.action` bo'yicha beriladi:

```python
BUGALTER_ACTIONS = {'approve', 'reject', 'confirm_payment'}

def get_permissions(self):
    if self.action in BUGALTER_ACTIONS:
        return [IsAdminOrBugalter()]
    return super().get_permissions()
```

3. `pk` doim `<int:pk>` — matnli manzillar (`in-transit`, `summary`, `deadlines`) bilan chalkashmaydi.
4. Nom berish: `<model>-list`, `<model>-detail`, `<model>-<amal>` (`contract-timeline`).
5. `app_name` qo'yilmaydi — endpoint nomlari global bo'lib qoladi.
6. Yangi ilova `apps/urls.py` ga bitta qator bilan qo'shiladi:

```python
path('', include('apps.<app>.urls')),
```

7. `root/urls.py` faqat `admin/`, `api/` (→ `apps.urls`) va schema/docs ni biladi — unga tegilmaydi.

---

## 7. Service qoidalari

```python
@atomic
def receive_purchase(purchase, user=None):
    """Kirimni qabul qiladi: ombor qoldigi va kassa chiqimi yoziladi."""
    if purchase.status == Purchase.Status.RECEIVED:
        raise ValidationError('Bu kirim allaqachon qabul qilingan.')
    ...
```

- Bir nechta modelga tegadigan amal — `@atomic`.
- Xatolik `rest_framework.exceptions.ValidationError` / `PermissionDenied` bilan qaytariladi
  (view ularni avtomatik 400/403 ga aylantiradi).
- Xato matnlari o'zbekcha.

---

## 8. Testlar

- Har bir ilovada `tests/` paketi, fayl nomi `test_<nima>.py`.
- API testlari uchun `rest_framework.test.APITestCase` + `self.client.force_authenticate(user)`.
- Har bir biznes qoida uchun kamida bitta test (foizlar, ranglar, rol ruxsatlari, qoldiq).
- Test klassi va metodlariga o'zbekcha docstring.

---

## 9. Umumiy

| Qoida | Izoh |
|---|---|
| Qator uzunligi | ~100 belgigacha |
| Qo'shtirnoq | `'single'` (matn ichida apostrof bo'lsa `"double"`) |
| Ro'yxatlar | oxirgi elementdan keyin vergul (`trailing comma`) |
| Nom berish | model — `PascalCase`, maydon/funksiya — `snake_case`, konstanta — `UPPER_CASE` |
| Kommentariya | faqat "nega" degan joyda, o'zbekcha |
| Migratsiya | model o'zgarsa darhol `makemigrations` |
