"""Barcha ilovalarning marshrutlarini bitta joyda yig'adi.

Router ishlatilmaydi — har bir ilova o'z `urls.py` sida manzillarni `path()` bilan
aniq yozadi, bu yerda esa ular ketma-ket ulanadi.
"""

from django.urls import include, path

urlpatterns = [
    path('', include('apps.accounts.urls')),
    path('', include('apps.clients.urls')),
    path('', include('apps.inventory.urls')),
    path('', include('apps.configurator.urls')),
    path('', include('apps.purchases.urls')),
    path('', include('apps.sales.urls')),
    path('', include('apps.finance.urls')),
    path('', include('apps.core.urls')),
]
