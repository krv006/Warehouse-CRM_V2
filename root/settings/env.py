"""Muhit o'zgaruvchilarini o'qish uchun kichik yordamchilar.

Server (.env fayli) qiymat bermasa, loyiha default qiymati ishlaydi —
shuning uchun lokal ishga tushirish uchun hech narsa sozlash shart emas.
"""

import os

TRUE_VALUES = {'1', 'true', 'yes', 'on'}


def env_str(name, default=''):
    return os.environ.get(name, default).strip()


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in TRUE_VALUES


def env_list(name, default=''):
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(',') if item.strip()]
