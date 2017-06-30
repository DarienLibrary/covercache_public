import requests
from base64 import b64encode
from django.conf import settings


class OverdriveAPI(object):

    website_id = settings.OVERDRIVE['website_id']
    library_id = settings.OVERDRIVE['library_id']
    authorization_name = settings.OVERDRIVE['authorization_name']
    client_id = settings.OVERDRIVE['client_id']
    client_secret = settings.OVERDRIVE['client_secret']
    collection_id = settings.OVERDRIVE['collection_id']

    def __init__(self, barcode=None):
        self.has_token = False

    def _exec_request(self, http_method, root_uri, suffix_uri, **kwargs):
        # This is the heart of the API wrapper. All the Overdrive API methods
        # take their method specific input and parse it and call this method
        # which then constructs and sends the appropriate request.
        params = kwargs.get('params', {})
        if not self.has_token and not self._get_token():
            return
        uri = root_uri + suffix_uri
        headers = {
            'Authorization': '{token_type} {access_token}'.format(
                token_type=self.token_type.title(),
                access_token=self.access_token),
            'Content-Type': 'application/json; charset=utf-8'
        }
        data = kwargs.get('data', '')
        return requests.request(
            http_method,
            uri,
            headers=headers,
            data=data,
            params=params,
        )

    def _get_token(self):
        signature = b64encode('{}:{}'.format(
            self.client_id,
            self.client_secret).encode('utf-8')).decode('ascii')
        headers = {
            'Authorization': 'Basic {signature}'.format(signature=signature),
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
        }
        data = "grant_type=client_credentials"
        uri = "https://oauth.overdrive.com/token"
        res = requests.post(uri, headers=headers, data=data)
        if res.status_code == 200:
            token_info = res.json()
            self.access_token = token_info['access_token']
            self.token_type = token_info['token_type']
            self.has_token = True
        else:
            self.has_token = False
        return self.has_token

    def get_metadata(self, item_id):
        http_method = 'GET'
        root_uri = 'http://integration.api.overdrive.com'
        suffix_uri = '/v1/collections/{collection_id}/products/{item_id}/metadata'.format(
            collection_id=self.collection_id,
            item_id=item_id)
        return self._exec_request(
            http_method=http_method,
            root_uri=root_uri,
            suffix_uri=suffix_uri)