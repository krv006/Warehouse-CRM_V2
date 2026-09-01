"""Asosiy Django sozlamalari: ilovalar, middleware, shablonlar, til va fayllar."""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from root.settings.env import env_bool, env_int, env_list, env_str

# root/settings/base.py -> root/settings -> root -> loyiha ildizi
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Serverda .env orqali beriladi, lokalda default ishlaydi
SECRET_KEY = env_str(
    'SECRET_KEY',
    'django-insecure-tti2@f27gu7arts#0=1wv283t&0ji3)b7wgp60)@@f=5+gdc*t',
)

# Serverda: DEBUG=False
DEBUG = env_bool('DEBUG', True)

# Prod'da zaif kalit bilan ishga tushirish mumkin emas — deploy skripti
# (.env yaratilganda) kuchli kalitni o'zi generatsiya qiladi
if not DEBUG and ('insecure' in SECRET_KEY or len(SECRET_KEY) < 32):
    raise ImproperlyConfigured(
        "SECRET_KEY zaif yoki default holatda. .env ga kuchli kalit qo'ying: "
        'python -c "from django.core.management.utils import '
        'get_random_secret_key; print(get_random_secret_key())"'
    )

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', '*')

# Domen orqali admin panelga kirish uchun (masalan: https://crm.example.uz)
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')

# ------------------------------------------------ prod xavfsizlik sozlamalari
# Sayt HTTPS ortida (Caddy) ishlaydi — cookie'lar faqat HTTPS orqali yuriladi.
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_REFERRER_POLICY = 'same-origin'
    # HSTS: brauzer domenni faqat HTTPS'da ochadi (default 30 kun, .env da o'zgaradi)
    SECURE_HSTS_SECONDS = env_int('SECURE_HSTS_SECONDS', 2592000)

SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = 'DENY'


# Ilovalar

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
]

LOCAL_APPS = [
    'apps.core',
    'apps.accounts',
    'apps.clients',
    'apps.inventory',
    'apps.configurator',
    'apps.purchases',
    'apps.procurement',
    'apps.sales',
    'apps.finance',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # Static fayllarni ilovaning o'zi beradi — nginx/Caddy sozlanmagan bo'lsa ham ishlaydi
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'root.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'root.wsgi.application'
ASGI_APPLICATION = 'root.asgi.application'


# Til va vaqt
LANGUAGE_CODE = 'uz'
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('uz', "O'zbekcha"),
    ('ru', 'Русский'),
    ('en', 'English'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']


# Static va media
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Oldida reverse proxy (Caddy/nginx) turganda: HTTPS ni to'g'ri aniqlash uchun.
# Proxy X-Forwarded-Proto sarlavhasini yuboradi, aks holda DRF havolalari http:// bo'lib qoladi.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

# Media fayllarni Django o'zi bersinmi (oldida fayl serveri bo'lmasa — ha)
SERVE_MEDIA = env_bool('SERVE_MEDIA', True)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
