from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class CheckerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'checker'
    verbose_name = 'AI Disease Recognizer'

    def ready(self):
        logger.info("AI Disease Recognizer v2.0 Loaded Successfully")
