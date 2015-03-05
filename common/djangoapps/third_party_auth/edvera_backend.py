from social.backends.oauth import BaseOAuth2

from django.conf import settings

from . import provider
import logging

logger = logging.getLogger(__name__)


class EdveraOAuth2(BaseOAuth2):
    """Edvera authentication backend"""

    name = 'edvera-oauth2'

    REDIRECT_STATE = False

    DEFAULT_SITE = 'http://wqu-agency.edvera.dev:3000/'

    SITE = getattr(settings, 'EDVERA_SITE', DEFAULT_SITE)

    AUTHORIZATION_URL = SITE + 'oauth/authorize'

    ACCESS_TOKEN_URL = SITE + 'oauth/token'
    ACCESS_TOKEN_METHOD = 'POST'

    REVOKE_TOKEN_URL = SITE + 'oauth/revoke'
    REVOKE_TOKEN_METHOD = 'POST'

    # The order of the default scope is important

    DEFAULT_SCOPE = ['write', 'public', 'update']

    def revoke_token_params(self, token, uid):
        return {'token': token}

    def revoke_token_headers(self, token, uid):
        return {'Content-type': 'application/json'}

    def get_user_id(self, details, response):
        return response.get('user')['id']

    def get_user_details(self, response):
        user = response.get('user', {})
        return {'email': user['email'],
                'fullname': user['first_name'] + ' ' + user['last_name'],
                'username': user['first_name']}

    def user_data(self, access_token, *args, **kwargs):
        return self.get_json(self.SITE + 'users/current', params={
            'access_token': access_token
        })


class EdveraProvider(provider.BaseProvider):
    """Provider for EDvera's Oauth2 auth system."""

    BACKEND_CLASS = EdveraOAuth2
    ICON_CLASS = None
    NAME = 'Edvera'
    SETTINGS = {
        'SOCIAL_AUTH_EDVERA_OAUTH2_KEY': None,
        'SOCIAL_AUTH_EDVERA_OAUTH2_SECRET': None,
    }

    @classmethod
    def get_email(cls, provider_details):
        return provider_details.get('email')

    @classmethod
    def get_name(cls, provider_details):
        return provider_details.get('fullname')
