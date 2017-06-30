from celery import shared_task

from django.conf import settings

from . import utils
from .models import Identifier
from .sources import get_source


@shared_task
def maintain():
    utils.update_altered_manifestation_ids()
    utils.prune_manifestations()
    utils.update_identifiers()
    utils.update_works()
    utils.try_to_download_covers()


@shared_task
def get_recommendations(identifier_id):
    try:
        identifier = Identifier.objects.get(pk=identifier_id)
    except Identifier.DoesNotExist:
        return []
    source = get_source(settings.RECOMMENDATIONS['source'])()
    return source.get_recommendations(identifier)
