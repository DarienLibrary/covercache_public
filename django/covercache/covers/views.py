import requests
from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.decorators import detail_route, list_route
from rest_framework import status
from rest_framework_extensions.cache.decorators import cache_response

from collections import OrderedDict
from django.conf import settings

from .models import Work, Manifestation, Identifier, Cover
from .sources import Staff
from .serializers import WorkSerializer, CoverSerializer


class WorkViewSet(ViewSet):
    queryset = Work.objects.all()

    def _calculate_cache_key(view_instance, view_method, request, args, kwargs):
        return request.path

    def retrieve(self, request, pk=None):
        try:
            work = Work.objects.get(pk=pk)
        except Work.DoesNotExist:
            resp = {
                "covers": [],
                "success": False
            }
            return Response(resp, status=status.HTTP_404_NOT_FOUND)
        covers = CoverSerializer(work.get_covers(), many=True)
        resp = {
            "covers": covers.data,
            "success": True
        }
        return Response(resp, status=status.HTTP_200_OK)

    @detail_route(methods=['post'])
    def poll_sources(self, request, pk=None):
        try:
            work = Work.objects.get(pk=pk)
        except Work.DoesNotExist:
            return Response({}, status=status.HTTP_404_NOT_FOUND)

        if not work.has_cover():
            work.try_to_download_cover()
        return Response({}, status=status.HTTP_200_OK)

    @detail_route(methods=['post'])
    def override(self, request, pk=None):
        try:
            work = Work.objects.get(pk=pk)
        except Work.DoesNotExist:
            return Response({}, status=status.HTTP_404_NOT_FOUND)

        manifestations = work.manifestations.order_by()
        if not manifestations.count():
            return Response({}, status=status.HTTP_400_BAD_REQUEST)
        manifestation = manifestations[0]

        url = request.data.get('url')
        try:
            requests.get(url)
        except requests.exceptions.RequestException:
            return Response({}, status=status.HTTP_400_BAD_REQUEST)

        try:
            identifier = Identifier.objects.get(
                source='staff',
                value=url
            )
            return Response({}, status=status.HTTP_400_BAD_REQUEST)
        except Identifier.DoesNotExist:
            identifier = Identifier(
                source='staff',
                value=url
            )

        covers = None
        if identifier.id:
            # if the identifier existed before the request
            covers = identifier.covers.all()
        if not covers:
            source = Staff()
            identifier.try_to_download_cover(source)
            covers = identifier.covers.all()
        if covers:
            manifestation.identifiers.add(identifier)
            resp = CoverSerializer(covers, many=True).data
            return Response(resp, status=status.HTTP_200_OK)
        else:
            identifier.delete()
            return Response({}, status=status.HTTP_400_BAD_REQUEST)

    @list_route(methods=['get'])
    def stats(self, request):
        works_with_covers = Work.objects.filter(
            manifestations__identifiers__covers__isnull=False).count()
        works_with_no_way_to_get_covers = Work.objects.filter(
            manifestations__identifiers=None).exclude(
                manifestations__in=Manifestation.objects.exclude(
                    identifiers=None)).count()
        covers_by_source = OrderedDict([
            (source, Cover.objects.filter(source=source).count())
            for source in settings.SOURCE_PRECEDENCE
        ])
        identifiers_by_source = {
            source: Identifier.objects.filter(source=source).count()
            for source
            in Identifier.objects.values_list('source', flat=True).distinct()
        }
        works_with_no_covers = Work.objects.exclude(
            manifestations__identifiers__covers__isnull=False)
        identifiers_of_works_with_no_covers = Identifier.objects.filter(
            manifestations__work__in=works_with_no_covers)
        worthless_identifiers_by_source = {
            source: identifiers_of_works_with_no_covers.filter(
                source=source).count()
            for source
            in Identifier.objects.values_list('source', flat=True).distinct()
        }

        resp = OrderedDict([
            ('works', Work.objects.all().count()),
            ('manifestations', Manifestation.objects.all().count()),
            ('identifiers', Identifier.objects.all().count()),
            ('covers', Cover.objects.all().count()),
            ('works_with_covers', works_with_covers),
            ('works_with_no_way_to_get_covers', works_with_no_way_to_get_covers),
            ('identifiers_by_source', identifiers_by_source),
            ('worthless_identifiers_by_source', worthless_identifiers_by_source),
            ('covers_by_source', covers_by_source)
        ])
        return Response(resp, status=status.HTTP_200_OK)

    @detail_route(methods=['get'])
    @cache_response(
        settings.RECOMMENDATIONS['cache_response_timeout'],
        key_func=_calculate_cache_key
    )
    def recommendations(self, request, pk=None):
        try:
            work = Work.objects.get(pk=pk)
        except Work.DoesNotExist:
            return Response({}, status=status.HTTP_404_NOT_FOUND)

        recommendations = WorkSerializer(work.get_recommendations(), many=True)
        resp = {
            "recommendations": recommendations.data,
            "success": True
        }
        return Response(resp, status=status.HTTP_200_OK)
