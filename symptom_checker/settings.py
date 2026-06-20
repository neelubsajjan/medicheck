+ from pathlib import Path
+ import os
+ from dotenv import load_dotenv

+ BASE_DIR = Path(_file_).resolve().parent.parent
+ # Load enviroonment variables from .env file
+ SECRET_KEY = 'django-insecure-mediAI-v2-key-xyz123'
+ DEBUG = True
+ ALLOWED_HOSTS = ['*']

+ INSTALLED_APPS = [
+     'checker',
+ ]

+ WSGI_APPLICATION = 'symptom_checker.wsgi.application'

+ DATABASES = {
+     'default': {
+         'ENGINE': 'django.db.backends.sqlite3',
+         'NAME': BASE_DIR / 'db.sqlite3',
+     }
+ }

+ MONGODB_HOST = 'localhost'
+ MONGODB_PORT = 27017
+ MONGODB_DB = 'mediAI_db'

+ STATIC_URL = '/static/'
+ STATIC_ROOT = BASE_DIR / 'staticfiles'

+ MEDIA_URL = '/media/'
+ MEDIA_ROOT = BASE_DIR / 'media'

+ ML_MODELS_DIR = BASE_DIR / 'ml_models'

+ load_dotenv(str(BASE_DIR / '.env'))

+ GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

+ EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
+ EMAIL_FILE_PATH = BASE_DIR / 'sent_emails'
