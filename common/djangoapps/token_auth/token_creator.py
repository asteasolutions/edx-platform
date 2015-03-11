from urlparse import urlparse
from requests.api import request

from provider.oauth2.models import Client, AccessToken

from social.pipeline import partial


def get_base_url(redirect_url):
    parsed_result = urlparse(redirect_url)
    return parsed_result.scheme + '://' + parsed_result.netloc + '/'


@partial.partial
def send_access_token(strategy, user=None, is_dashboard=False, *args, **kwargs):
    edx_id = user.username
    endpoint_url = get_base_url(kwargs['backend'].redirect_uri)
    edx_access_token = kwargs['response']['access_token']
    site = kwargs['backend'].SITE

    client = Client(user=user, name=edx_id, redirect_uri='none', url=site, client_type=2)
    client.save()

    access_token = AccessToken(client=client, user=user)
    access_token.save()

    request('POST', site + 'course_resource/edx/accounts',
            params={'access_token': edx_access_token, 'edx_id': edx_id, 'endpoint_url': endpoint_url,
                    'api_token': access_token.token})
