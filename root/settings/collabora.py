"""15-§A: Collabora Online (WOPI) — shartnoma `.docx`ni brauzerda tahrirlash.

`COLLABORA_URL` — Collabora Online konteynerining o'zi (iframe shu yerdan
ochiladi). `WOPI_PUBLIC_URL` — Collabora BIZNING backendga (WOPI host)
qaytib ulanadigan tashqi manzil — lokal ishga tushirishda ikkalasi ham
bo'sh qolishi mumkin (funksiya .docx yuklanmaguncha chaqirilmaydi).
"""

from root.settings.env import env_str

COLLABORA_URL = env_str('COLLABORA_URL', 'http://localhost:9980')
WOPI_PUBLIC_URL = env_str('WOPI_PUBLIC_URL', 'http://localhost:8000')

# WOPI access token muddati (daqiqa) — Collabora bu muddatda faylni ochib
# turadi, muddat tugasa REFRESH_LOCK bilan LOCK yangilanadi (u tokenni
# qayta tekshirmaydi, shuning uchun token muddati LOCK muddatidan uzunroq)
WOPI_TOKEN_TTL_MINUTES = 180
# WOPI LOCK muddati (daqiqa) — spetsifikatsiya bo'yicha standart 30 daqiqa
WOPI_LOCK_TTL_MINUTES = 30
