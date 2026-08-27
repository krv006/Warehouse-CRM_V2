"""Ma'lumotlar bazasi sozlamalari.

Default — loyiha ildizidagi SQLite. Serverda (Docker) baza volume ichida turadi:
`SQLITE_PATH=/app/data/db.sqlite3`.
"""

from pathlib import Path

from root.settings.base import BASE_DIR
from root.settings.env import env_str

SQLITE_PATH = env_str('SQLITE_PATH') or str(BASE_DIR / 'db.sqlite3')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': Path(SQLITE_PATH),
    }
}
