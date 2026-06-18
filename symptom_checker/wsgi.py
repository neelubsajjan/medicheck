import os
import logging
from django.core.wsgi import get_wsgi_application

# Logging Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set Default Settings Module
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'symptom_checker.settings'
)

# Initialize WSGI Application
application = get_wsgi_application()

# Startup Log
logger.info("AI Disease Recognizer v2.0 started successfully")
