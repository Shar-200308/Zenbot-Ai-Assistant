# Load the Celery app when Django starts so tasks are always registered.
from .celery import app as celery_app

__all__ = ('celery_app',)
