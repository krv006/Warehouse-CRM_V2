"""Marshrutlar uchun standart HTTP metod xaritalari.

Router ishlatilmaydi — har bir manzil `path()` bilan aniq yoziladi,
bu xaritalar shunchaki takrorlanadigan lug'atlarni bir joyda saqlaydi.

    path('products/', ProductViewSet.as_view(LIST), name='product-list')
"""

# To'liq CRUD
LIST = {
    'get': 'list',
    'post': 'create',
}
DETAIL = {
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
}

# Faqat o'qish uchun (audit, tasdiqlash tarixi, eslatmalar)
READ_LIST = {'get': 'list'}
READ_DETAIL = {'get': 'retrieve'}
