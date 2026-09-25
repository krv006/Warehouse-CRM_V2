"""Sozlamalar paketi — har bir bo'lak alohida faylda.

    base.py         asosiy Django sozlamalari
    database.py     ma'lumotlar bazasi
    auth.py         foydalanuvchi modeli va parol tekshiruvlari
    rest.py         Django REST Framework
    jwt.py          JWT (simplejwt) token sozlamalari
    spectacular.py  OpenAPI hujjati
    cors.py         React dev server uchun CORS
    business.py     TZ dagi biznes raqamlari
"""

from root.settings.base import *          # noqa: F401,F403
from root.settings.database import *      # noqa: F401,F403
from root.settings.auth import *          # noqa: F401,F403
from root.settings.rest import *          # noqa: F401,F403
from root.settings.jwt import *           # noqa: F401,F403
from root.settings.spectacular import *   # noqa: F401,F403
from root.settings.cors import *          # noqa: F401,F403
from root.settings.business import *      # noqa: F401,F403
