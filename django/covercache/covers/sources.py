from PIL import Image
import requests

from hashlib import sha256
import re
import time
from io import BytesIO
import hashlib

from django.core.files import File
from django.conf import settings

from covercache.overdrive import OverdriveAPI


def get_sources():
    sources = {
        'amazon': Amazon,
        'bibliotheca': Bibliotheca,
        # 'librarything': Librarything,
        'link': Link,
        'overdrive': Overdrive,
        'syndetics': Syndetics,
        'worldcat': Worldcat,
        'zola': Zola
    }
    for source_name in settings.SOURCE_PRECEDENCE:
        if sources.get(source_name):
            yield sources[source_name]


def get_source(source_name):
    sources = {
        'amazon': Amazon,
        'bibliotheca': Bibliotheca,
        # 'librarything': Librarything,
        'link': Link,
        'overdrive': Overdrive,
        'syndetics': Syndetics,
        'worldcat': Worldcat,
        'zola': Zola
    }
    if source_name in sources.keys():
        return sources[source_name]


class ImageSource(object):

    def get_cover(self, identifier):
        image_url = self.get_image_url(identifier)
        if image_url:
            try:
                response = requests.get(image_url)
            except requests.exceptions.RequestException:
                return
            if self.validate_image_url_response(response):
                input_bytes = BytesIO(response.content)
                try:
                    image = Image.open(input_bytes)
                except OSError:
                    # in case sources return files that are not images
                    return
                if image.width >= settings.IMAGE_WIDTH:
                    size = (
                        settings.IMAGE_WIDTH,
                        int(settings.IMAGE_WIDTH * image.height / image.width))
                    image = image.resize(size, Image.ANTIALIAS)
                    output_bytes = BytesIO()
                    image.save(output_bytes, 'JPEG')
                    filename = self.get_filename(identifier)
                    f = File(output_bytes, filename)
                    print('{} provided {}'.format(
                        self.source,
                        filename
                    ))
                    return f

    def get_filename(self, identifier):
        return '{}_{}_{}.jpg'.format(
            identifier.source,
            identifier.value,
            str(int(time.time())),
        )


class Amazon(ImageSource):

    source = 'amazon'

    def get_image_url(self, identifier):
        url = None
        if identifier.source == 'isbn':
            isbn10 = self._isbn_convert_13_to_10(identifier.value)
            url = "http://images.amazon.com/images/P/{isbn}.01.20TRZZZZ_.jpg".format(
                isbn=isbn10)
        return url

    def validate_image_url_response(self, response):
        return response.status_code == 200

    def _isbn_convert_13_to_10(self, isbn):
        prefix = isbn[3:-1]
        check = self._isbn10_check_digit(prefix)
        return prefix + check

    def _isbn10_check_digit(self, isbn):
        assert len(isbn) == 9
        sum = 0
        for i in range(len(isbn)):
            c = int(isbn[i])
            w = i + 1
            sum += w * c
        r = sum % 11
        if r == 10:
            return 'X'
        else:
            return str(r)


class Bibliotheca(ImageSource):

    source = 'bibliotheca'

    def get_image_url(self, identifier):
        url = None
        if identifier.source == 'bibliotheca':
            url = "http://ebook.3m.com/delivery/img?type=DOCUMENTIMAGE&documentID={bibliotheca_id}&size=LARGE".format(
                bibliotheca_id=identifier.value)
        return url

    def validate_image_url_response(self, response):
        return response.status_code == 200


class Link(ImageSource):

    source = 'link'

    def get_image_url(self, identifier):
        url = None
        if identifier.source == 'link':
            url = identifier.value
        return url

    def validate_image_url_response(self, response):
        return response.status_code == 200

    def get_filename(self, identifier):
        return '{}_{}.jpg'.format(
            identifier.source,
            str(int(time.time())),
        )


class Overdrive(ImageSource):

    source = 'overdrive'

    def get_image_url(self, identifier):
        url = None
        if identifier.source == 'overdrive':
            o = OverdriveAPI()
            res = o.get_metadata(identifier.value)
            if res.status_code == 200:
                try:
                    url = res.json()['images']['cover']['href']
                except KeyError:
                    pass
        return url

    def validate_image_url_response(self, response):
        return response.status_code == 200


class Staff(ImageSource):

    source = 'staff'

    def get_image_url(self, identifier):
        url = None
        if identifier.source == 'staff':
            url = identifier.value
        return url

    def validate_image_url_response(self, response):
        return response.status_code == 200

    def get_filename(self, identifier):
        return '{}_{}.jpg'.format(
            identifier.source,
            str(int(time.time())),
        )


class Syndetics(ImageSource):

    source = 'syndetics'
    client_id = settings.SYNDETICS['client_id']

    def get_image_url(self, identifier):
        url = None
        if identifier.source == 'isbn':
            url = "http://syndetics.com/index.aspx?isbn={isbn}/lc.jpg&client={client_id}".format(
                isbn=identifier.value,
                client_id=self.client_id)
        return url

    def validate_image_url_response(self, response):
        return response.headers['content-type'].startswith('image')


class Worldcat(ImageSource):

    source = 'worldcat'
    default_image_hash = settings.WORLDCAT['default_image_hash']

    def get_image_url(self, identifier):
        url = None
        if identifier.source == 'oclc':
            try:
                res = requests.get('http://www.worldcat.org/oclc/{oclc}'.format(
                    oclc=identifier.value
                ))
            except requests.exceptions.RequestException:
                return
            exp = r'coverart\.oclc\.org/ImageWebSvc/oclc/\+-\+(\d+)_140\.jpg'
            if res.status_code == 200:
                m = re.search(exp, res.content.decode(res.encoding))
                if m:
                    image_id = m.group(1)
                    url = 'http://coverart.oclc.org/ImageWebSvc/oclc/+-+{image_id}_400.jpg'.format(
                        image_id=image_id)
        return url

    def validate_image_url_response(self, response):
        return sha256(response.content).hexdigest() != self.default_image_hash


class Zola(ImageSource):

    source = 'zola'
    key = settings.ZOLA['key']
    secret = settings.ZOLA['secret']
    default_image_hash = settings.ZOLA['default_image_hash']

    def get_signature(self):
        timestamp = str(int(time.time()))
        hashed = hashlib.md5(
            (self.key + self.secret + timestamp).encode('utf-8')
        )
        signature = hashed.hexdigest()
        return signature

    def get_recommendations(self, identifier):
        from .models import Identifier, Work
        isbns = []
        if identifier.source == 'isbn':
            url = 'https://api.zo.la/v4/recommendation/rec?action=get&isbn={isbn}&key={key}&signature={signature}&limit={limit}'.format(
                isbn=identifier.value,
                key=self.key,
                signature=self.get_signature(),
                limit=settings.RECOMMENDATIONS['recommendations_per_identifier'])
            raw_res = requests.get(url)
            if raw_res.status_code == 200:
                res = raw_res.json()
                if res['status'] == 'success' and res.get('data'):
                    for item in res['data'].get('list', []):
                        for isbn in item.get('version_isbns', []):
                            isbns.append(isbn)
        recommended_work_ids = list(Work.objects.filter(
            manifestations__identifiers__covers__isnull=False,
            manifestations__identifiers__in=Identifier.objects.filter(
                source='isbn',
                value__in=isbns)).values_list(
                    'pk',
                    flat=True))
        return recommended_work_ids

    def get_additional_information(self, identifier):
        if identifier.source == 'isbn':
            url = 'https://api.zo.la/v4/metadata/details?action=book&isbn={isbn}&key={key}&signature={signature}'.format(
                isbn=identifier.value,
                key=self.key,
                signature=self.get_signature())
            raw_res = requests.get(url)
            if raw_res.status_code == 200:
                res = raw_res.json()
                if res['status'] == 'success':
                    return res['data']

    def get_image_url(self, identifier):
        url = None
        if identifier.source == 'isbn':
            url = 'https://api.zo.la/v4/image/display?id={isbn}'.format(
                isbn=identifier.value)
        return url

    def validate_image_url_response(self, response):
        return sha256(response.content).hexdigest() != self.default_image_hash
