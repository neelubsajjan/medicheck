import os
import logging
from django.core.wsgi import get_wsgi_application

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("symptom_checker")

# Environment Configuration
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "symptom_checker.settings"
)

# WSGI Application
application = get_wsgi_application()

# Startup Information
logger.info("===================================")
logger.info(" AI Disease Recognizer v2.1")
logger.info(" WSGI Server Started Successfully")
logger.info(f" Environment : {os.getenv('DJANGO_SETTINGS_MODULE')}")
logger.info("===================================")
