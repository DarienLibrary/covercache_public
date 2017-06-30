from celery import group
from datetime import timedelta
import itertools
import operator
import time

from django.db import models
from django.conf import settings
from django.utils import timezone

from . import sources
from covercache import connector


class Work(models.Model):
    id = models.IntegerField(primary_key=True)

    def has_cover(self):
        return bool(Cover.objects.filter(
            identifier__in=Identifier.objects.filter(
                manifestations__in=self.manifestations.all())).count())

    def get_identifiers(self):
        sorted_identifiers = []
        for manifestation in self.manifestations.order_by():
            for identifier in manifestation.identifiers.all():
                if identifier not in sorted_identifiers:
                    sorted_identifiers.append(identifier)
        return sorted_identifiers

    def get_covers(self):
        covers = list(Cover.objects.filter(
            identifier__in=Identifier.objects.filter(
                manifestations__in=self.manifestations.all())))
        covers.sort(key=operator.methodcaller('get_precedence'))
        return covers

    def try_to_download_cover(self):
        identifiers = self.get_identifiers()
        for Source in sources.get_sources():
            source = Source()
            for identifier in identifiers:
                cover = identifier.try_to_download_cover(source)
                if cover:
                    return cover

    def get_recommendations(self):
        from . import tasks
        identifiers = Identifier.objects.filter(
            source='isbn',
            manifestations__in=self.manifestations.all())
        grouped_identifier_ids = group(
            tasks.get_recommendations.s(i.pk)
            for i in identifiers)().get()
        result_identifier_ids = itertools.chain.from_iterable(grouped_identifier_ids)
        works = Work.objects.filter(pk__in=result_identifier_ids)
        return works


class Identifier(models.Model):
    source = models.CharField(max_length=32)
    value = models.CharField(max_length=256)
    date_last_checked = models.DateTimeField(null=True)

    def has_cover(self):
        return bool(self.covers.all())

    def try_to_download_cover(self, source):
        if not self.date_last_checked or self.date_last_checked < timezone.now() - timedelta(days=settings.RETRY_PERIOD):
            self.date_last_checked = timezone.now()
            self.save()
            identifier = self
            file = source.get_cover(identifier)
            if file:
                cover = Cover(
                    source=source.source,
                    identifier=self,
                )
                cover.image.save(
                    name=file.name,
                    content=file,
                    save=True)
                return cover


class Manifestation(models.Model):
    id = models.IntegerField(primary_key=True)
    date_last_checked = models.DateTimeField(null=True)
    precedence = models.IntegerField()

    work = models.ForeignKey(
        Work,
        related_name='manifestations',
        null=True)

    identifiers = models.ManyToManyField(
        Identifier,
        related_name='manifestations')

    def has_cover(self):
        return bool(Cover.objects.filter(
            identifier__in=self.identifiers.all()).count())

    def map_identifiers(self):
        identifiers = list(self.identifiers.filter(source='staff'))
        identifier_attributes = connector.get_identifiers(self.id)
        for identifier_attribute in identifier_attributes:
            try:
                identifier = Identifier.objects.get(
                    value=identifier_attribute['value'],
                    source=identifier_attribute['source'])
            except Identifier.DoesNotExist:
                identifier = Identifier(
                    value=identifier_attribute['value'],
                    source=identifier_attribute['source'])
                identifier.save()
            identifiers.append(identifier)
        self.identifiers.clear()
        self.identifiers.add(*identifiers)
        self.date_last_checked = timezone.now()
        self.save()

    class Meta:
        ordering = ['-precedence', '-id']


class Cover(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    source = models.CharField(max_length=32, null=True)
    image = models.ImageField(upload_to='covers/')

    identifier = models.ForeignKey(
        Identifier,
        related_name='covers')

    def get_precedence(self):
        return (
            settings.SOURCE_PRECEDENCE.index(self.source),
            -time.mktime(self.date_created.timetuple()),
            -self.image.width,
        )
