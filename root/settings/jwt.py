"""JWT (simplejwt) sozlamalari.

Login:   POST /api/auth/login/    {username, password} -> {access, refresh}
Yangilash: POST /api/auth/refresh/  {refresh}          -> {access, refresh}
So'rov sarlavhasi: Authorization: Bearer <access>
"""

from datetime import timedelta

# Token muddatlari
ACCESS_TOKEN_LIFETIME = timedelta(hours=12)
REFRESH_TOKEN_LIFETIME = timedelta(days=7)

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': ACCESS_TOKEN_LIFETIME,
    'REFRESH_TOKEN_LIFETIME': REFRESH_TOKEN_LIFETIME,

    # Har bir refresh'da yangi refresh token beriladi
    'ROTATE_REFRESH_TOKENS': True,

    # Sarlavha ko'rinishi: "Authorization: Bearer <token>"
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',

    # Token ichidagi foydalanuvchi identifikatori
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}
