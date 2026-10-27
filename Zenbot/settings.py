import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

# ================= BASE DIR (ONLY ONE) =================
BASE_DIR = Path(__file__).resolve().parent.parent


# ================= SECURITY =================
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-dev-only-fallback-key')

DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

# Trust headers from Cloudflare/ngrok tunnels so generated URLs match the public domain
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ── ALLOWED_HOSTS ─────────────────────────────────────────────────────────────
# In DEBUG mode: allow everything (local dev convenience).
# In production: read from ALLOWED_HOSTS env var (comma-separated list).
if DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    _hosts_env = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1')
    ALLOWED_HOSTS = [h.strip() for h in _hosts_env.split(',') if h.strip()]

# Always add the SITE_URL hostname (e.g. cloudflare/ngrok tunnel) if configured
_SITE_URL = os.getenv('SITE_URL', '').strip().rstrip('/')
if _SITE_URL:
    from urllib.parse import urlparse
    _parsed = urlparse(_SITE_URL)
    if _parsed.hostname and '*' not in ALLOWED_HOSTS and _parsed.hostname not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_parsed.hostname)

# ── CSRF_TRUSTED_ORIGINS (Critical for HTTPS tunnels & live domains) ───────────
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]
_CSRF_ORIGINS_ENV = os.getenv('CSRF_TRUSTED_ORIGINS', '')
if _CSRF_ORIGINS_ENV:
    for _orig in _CSRF_ORIGINS_ENV.split(','):
        _orig = _orig.strip()
        if _orig and _orig not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(_orig)

if _SITE_URL:
    _full_origin = _SITE_URL if _SITE_URL.startswith(('http://', 'https://')) else f"https://{_SITE_URL}"
    if _full_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_full_origin)


# ================= PRODUCTION SECURITY HEADERS =================
# These only activate when DEBUG=False (safe in development)
if not DEBUG:
    SECURE_SSL_REDIRECT = True                 # Force HTTPS
    SECURE_HSTS_SECONDS = 31536000             # 1 year HSTS
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True               # Session cookie only on HTTPS
    CSRF_COOKIE_SECURE = True                  # CSRF cookie only on HTTPS
    SECURE_CONTENT_TYPE_NOSNIFF = True         # Prevent MIME sniffing
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'

# ================= FIREBASE =================
FIREBASE_KEY_PATH = BASE_DIR / "firebase-service-account.json"


# ================= APPLICATIONS =================
INSTALLED_APPS = [
    'chatbot.apps.ChatbotConfig',
    'rest_framework',
    'drf_spectacular',                # Disadvantage #2 fix: OpenAPI 3.0 schema generation
    'django_celery_results',          # Stores Celery task results in Django DB
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]
# Bug 7 fix: Cloudinary apps inserted BEFORE staticfiles (order matters for storage backends)
# Done after media config block defines INSTALLED_APPS_EXTRA


# ================= MIDDLEWARE =================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ================= URLS =================
ROOT_URLCONF = 'Zenbot.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'chatbot' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'chatbot.context_processors.company_context',
            ],
        },
    },
]


# ================= WSGI =================
WSGI_APPLICATION = 'Zenbot.wsgi.application'


# ================= DATABASE =================
# Reads DATABASE_URL from .env — defaults to SQLite for local dev.
# To switch to PostgreSQL: set DATABASE_URL=postgresql://user:pass@localhost:5432/zenbot_db
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,  # Keep DB connections alive for 10 min (performance)
    )
}


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True
USE_TZ = True


STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'chatbot' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'


# ================= MEDIA / FILE STORAGE =================
# Auto-switches to Cloudinary cloud storage when CLOUDINARY_URL is set in .env.
# Falls back to local storage if not configured (safe for development).
# To enable cloud: add CLOUDINARY_URL=cloudinary://api_key:api_secret@cloud_name to .env
_CLOUDINARY_URL = os.getenv('CLOUDINARY_URL', '').strip()

if _CLOUDINARY_URL:
    # ── Cloudinary Cloud Storage (production) ──────────────────────────────────
    _parsed_cloud = _CLOUDINARY_URL.replace('cloudinary://', '')
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'
    CLOUDINARY_STORAGE = {'CLOUDINARY_URL': _CLOUDINARY_URL}
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'  # Local fallback root (unused in cloud mode)
    INSTALLED_APPS_EXTRA = ['cloudinary_storage', 'cloudinary']
else:
    # ── Local Storage (development) ────────────────────────────────────────────
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'
    INSTALLED_APPS_EXTRA = []

# Bug 7 fix: Insert Cloudinary apps BEFORE django.contrib.staticfiles (required order)
if INSTALLED_APPS_EXTRA:
    _sf_idx = INSTALLED_APPS.index('django.contrib.staticfiles')
    INSTALLED_APPS[_sf_idx:_sf_idx] = INSTALLED_APPS_EXTRA




DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ================= LOGGING =================
# Logs to both console (DEBUG+) and a rotating log file (WARNING+).
# Log file: logs/zenbot.log — auto-created if missing.
_LOG_DIR = BASE_DIR / 'logs'
_LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name} — {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '{levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'level': 'DEBUG',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': _LOG_DIR / 'zenbot.log',
            'maxBytes': 5 * 1024 * 1024,   # 5 MB per file
            'backupCount': 3,               # Keep 3 rotated files
            'formatter': 'verbose',
            'level': 'WARNING',             # Only warnings+ go to file
            'encoding': 'utf-8',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'DEBUG' if DEBUG else 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'chatbot': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}


# ================= EMAIL CONFIGURATION =================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "your-email@gmail.com")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "your-app-password")
DEFAULT_FROM_EMAIL = f"Zenbot Team <{EMAIL_HOST_USER}>"
HR_EMAIL = os.getenv("HR_EMAIL", EMAIL_HOST_USER)

# ================= COMPANY / BRANDING CONFIGURATION =================
COMPANY_NAME = os.getenv("COMPANY_NAME", "Zensar Technologies")
COMPANY_CAREERS_EMAIL = os.getenv("COMPANY_CAREERS_EMAIL", HR_EMAIL)

# Public base URL for one-click email links (set this to your ngrok URL when testing on phone)
# Example: SITE_URL=https://abc123.ngrok-free.app
SITE_URL = os.getenv('SITE_URL', '').strip().rstrip('/')

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


# ================= REST FRAMEWORK =================
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',  # Disadvantage #2 fix
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '10/minute',
        'user': '30/minute',
        'application_submit': '5/minute',
        'application_submit_anon': '2/minute',
        'chat': '20/minute',
        'chat_anon': '5/minute',
    }
}


# ================= SPECTACULAR (OpenAPI / Swagger) =================
# Disadvantage #2 fix: auto-generates OpenAPI 3.0 schema from all @api_view endpoints.
# Access docs at: /api/docs/ (Swagger UI) or /api/redoc/ (ReDoc)
SPECTACULAR_SETTINGS = {
    'TITLE': 'ZenBot HR Recruitment API',
    'DESCRIPTION': (
        'RESTful API for the ZenBot Campus Recruitment Platform.\n\n'
        'Covers: Firebase authentication, candidate applications, '
        'resume analysis (ATS scoring), HR panel management, '
        'job/internship postings, analytics, and AI chatbot.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,   # Hide the raw schema endpoint from Swagger UI
    'COMPONENT_SPLIT_REQUEST': True,
    'SCHEMA_PATH_PREFIX': '/api/',
}


# ================= SESSION =================
# Use DB-backed sessions explicitly; expire after 1 hour (enough for resume flow)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 3600  # 1 hour in seconds


# ================= CACHE =================
# DB-backed cache — stores pre-computed resume analyses between requests.
# Run: python manage.py createcachetable   (once, after migrate)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'zenbot_cache',   # Table name created by createcachetable
        'TIMEOUT': 3600,              # Cache entries expire after 1 hour
    }
}


# ================= CELERY =================
# Background tasks: automatically routes through PostgreSQL (via SQLAlchemy)
# or Redis, with fallback to SQLite only when no database is configured.
_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_REDIS_URL = os.getenv("REDIS_URL", "").strip()

if _REDIS_URL:
    CELERY_BROKER_URL = _REDIS_URL
elif _DATABASE_URL and ("postgres" in _DATABASE_URL or "postgresql" in _DATABASE_URL):
    # Route Celery broker directly through PostgreSQL using SQLAlchemy
    _pg_broker = _DATABASE_URL
    if _pg_broker.startswith("postgres://"):
        _pg_broker = "postgresql://" + _pg_broker[len("postgres://"):]
    if not _pg_broker.startswith("sqla+"):
        _pg_broker = "sqla+" + _pg_broker
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", _pg_broker)
else:
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", f"sqla+sqlite:///{BASE_DIR / 'celery_broker.sqlite'}")
CELERY_RESULT_BACKEND = 'django-db'               # Store results in DB
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TIMEZONE = TIME_ZONE                       # Use same timezone as Django
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300                      # Kill a task after 5 min (safety net)

# Fix: CELERY_TASK_ALWAYS_EAGER fallback
# When no real broker is configured (only SQLite fallback), run tasks synchronously
# in the same process instead of silently losing them on restart.
_using_sqlite_broker = CELERY_BROKER_URL.startswith('sqla+sqlite')
if _using_sqlite_broker:
    CELERY_TASK_ALWAYS_EAGER = True       # Tasks run inline — no worker needed
    CELERY_TASK_EAGER_PROPAGATES = True   # Exceptions propagate correctly in eager mode


# ================= COMPANY / TENANT BRANDING CONFIGURATION =================
COMPANY_NAME = os.getenv('COMPANY_NAME', 'Zensar Technologies')
PORTAL_TITLE = os.getenv('PORTAL_TITLE', 'ZenBot Career Portal')
COMPANY_TAGLINE = os.getenv('COMPANY_TAGLINE', 'Empowering Digital Transformation Through Talent')
HR_SUPPORT_EMAIL = os.getenv('HR_SUPPORT_EMAIL', 'campusrecruitment@zensar.com')


# ================= CAMPUS OFFICE ADDRESSES =================
# Disadvantage #8 fix: moved from email_utils.py (was hardcoded).
# Override any address via env var — no code deployment needed:
#   CAMPUS_ADDR_PUNE=Zensar Technologies Ltd, New Building, Pune 411014
CAMPUS_ADDRESS_MAP = {
    'bengaluru':   os.getenv(
        'CAMPUS_ADDR_BENGALURU',
        'Zensar Technologies Ltd, Level 4, Brigade Tech Park, Pattandur Agrahara Road, Whitefield, Bengaluru, Karnataka 560066',
    ),
    'hyderabad':   os.getenv(
        'CAMPUS_ADDR_HYDERABAD',
        'Zensar Technologies Ltd, 5th Floor, Cyber Pearl Building, Hitec City, Madhapur, Hyderabad, Telangana 500081',
    ),
    'chennai_dlf': os.getenv(
        'CAMPUS_ADDR_CHENNAI_DLF',
        'Zensar Technologies Ltd, Block 7, 3rd Floor, DLF IT Park, 1/124 Mount Poonamallee Road, Manapakkam, Chennai, Tamil Nadu 600089',
    ),
    'chennai_omr': os.getenv(
        'CAMPUS_ADDR_CHENNAI_OMR',
        'Zensar Technologies Ltd, Rajiv Gandhi Salai (OMR), Navalur, Chennai, Tamil Nadu 600130',
    ),
    'pune':        os.getenv(
        'CAMPUS_ADDR_PUNE',
        'Zensar Technologies Ltd, Zensar Knowledge Park, Plot #4, Kharadi, MIDC, Off Nagar Road, Pune, Maharashtra 411014',
    ),
}
