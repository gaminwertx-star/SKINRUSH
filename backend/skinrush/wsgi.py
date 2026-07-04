"""WSGI entry point for SKINRUSH."""
import os

from django.core.wsgi import get_wsgi_application

os.environ["DJANGO_SETTINGS_MODULE"] = "skinrush.settings"
application = get_wsgi_application()
