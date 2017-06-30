from __future__ import absolute_import

import os

from django.conf import settings

from celery.utils.log import get_task_logger
from celery import Celery

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'covercache.settings')
logger = get_task_logger(__name__)

app = Celery('covercache')
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(bind=True)
def debug_task(self):
    logger.info('Request: {0!r}'.format(self.request))
