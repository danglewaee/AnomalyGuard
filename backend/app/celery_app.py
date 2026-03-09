from celery import Celery

from app.config import settings

celery_app = Celery("anomalyguard", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC")

celery_app.autodiscover_tasks(["app"])
