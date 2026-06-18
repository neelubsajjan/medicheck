from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'django-insecure-mediAI-v2-key-xyz123'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'checker',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'symptom_checker.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]

WSGI_APPLICATION = 'symptom_checker.wsgi.application'

# Primary DB — SQLite (auth, profiles, checks)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# MongoDB — for chatbot history, multimodal refs, hospital data
MONGODB_HOST = 'localhost'
MONGODB_PORT = 27017
MONGODB_DB   = 'mediAI_db'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
_static_dir = BASE_DIR / 'checker' / 'static'
STATICFILES_DIRS = [_static_dir] if _static_dir.exists() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'

LOGIN_URL = '/login/'

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

ML_MODELS_DIR = BASE_DIR / 'ml_models'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Load project-local environment variables from .env (optional local override)
try:
    load_dotenv(str(BASE_DIR / '.env'))
except Exception:
    pass

# GEMINI API key (used by chatbot live AI). Prefer session or OS env; fall back to settings var.
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

# File Email Backend for local development (writes password reset emails to the sent_emails/ directory)
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = BASE_DIR / 'sent_emails'


