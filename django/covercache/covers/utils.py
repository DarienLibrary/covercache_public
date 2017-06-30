from covercache import connector
from .models import Work, Manifestation, Identifier, Cover


def update_altered_manifestation_ids():
    print('update_altered_manifestation_ids')
    id_mapping = connector.get_altered_manifestation_id_mapping()
    for manifestation in Manifestation.objects.filter(id__in=id_mapping.keys()):
        prev_id = manifestation.id
        try:
            manifestation = Manifestation.objects.get(id=id_mapping[manifestation.id])
        except Manifestation.DoesNotExist:
            manifestation.id = id_mapping[manifestation.id]
            manifestation.save()
        identifiers = Manifestation.objects.get(id=prev_id).identifiers.all()
        manifestation.identifiers.add(*identifiers)


def prune_manifestations():
    print('prune_manifestations')
    connector_manifestation_ids = set([
        manifestation_attributes['manifestation_id']
        for manifestation_attributes
        in connector.get_manifestations()
    ])
    local_manifestion_ids = set(Manifestation.objects.values_list('id', flat=True))
    dead_manifestation_ids = local_manifestion_ids - connector_manifestation_ids
    Manifestation.objects.filter(id__in=dead_manifestation_ids).delete()


def update_identifiers():
    print('update_identifiers')
    for manifestation_attributes in connector.get_manifestations():
        manifestation_id = manifestation_attributes['manifestation_id']
        date_updated = manifestation_attributes['date_updated']
        try:
            manifestation = Manifestation.objects.get(id=manifestation_id)
        except Manifestation.DoesNotExist:
            manifestation = Manifestation(
                id=manifestation_id,
                precedence=manifestation_attributes.get('precedence', 0))
            manifestation.save()
        if not manifestation.date_last_checked or date_updated > manifestation.date_last_checked:
            manifestation.map_identifiers()


def update_works():
    print('update_works')
    for k, v in connector.get_works().items():
        try:
            manifestation = Manifestation.objects.get(id=k)
        except Manifestation.DoesNotExist:
            manifestation = None
        if manifestation:
            try:
                work = Work.objects.get(id=v)
            except Work.DoesNotExist:
                work = Work(id=v)
                work.save()
            manifestation.work = work
            manifestation.save()


def try_to_download_covers():
    print('try_to_download_cover')
    coverless_works = Work.objects.exclude(
        manifestations__in=(Manifestation.objects.filter(
            identifiers__in=Identifier.objects.filter(
                covers__in=Cover.objects.all())))).order_by('?')
    for work in coverless_works:
        print(work.id)
        work.try_to_download_cover()
