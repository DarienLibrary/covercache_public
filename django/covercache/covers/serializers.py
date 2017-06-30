from rest_framework import serializers

from .models import Work, Cover


class CoverSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    width = serializers.SerializerMethodField()

    def get_url(self, obj):
        return obj.image.url

    def get_width(self, obj):
        return obj.image.width

    class Meta:
        model = Cover
        fields = [
            'url',
            'width',
        ]


class WorkSerializer(serializers.ModelSerializer):
    covers = serializers.SerializerMethodField()

    def get_covers(self, obj):
        return CoverSerializer(obj.get_covers(), many=True).data

    class Meta:
        model = Work
        fields = [
            'id',
            'covers',
        ]