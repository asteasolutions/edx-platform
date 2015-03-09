from social.backends.oauth import BaseOAuth2
from django.conf import settings
from . import provider
from urlparse import urlparse
from onelogin.saml2.response import OneLogin_Saml2_Response
from social.backends.base import BaseAuth

from logging import getLogger

log = getLogger(__name__)


class SAMLVerificationFailure(Exception):
    pass


class SAMLBaseAuth(BaseAuth):
    saml_response = None
    log.error('saml initialized')

    def auth_url(self):
        log.error('saml auth_url')
        url = saml.AuthRequest.create(
            assertion_consumer_service_url=self.setting('ASSERTION_CONSUMER_SERVICE_URL'),
            issuer=self.setting('ISSUER'),
            name_identifier_format=self.setting('NAME_IDENTIFIER_FORMAT'),
            idp_sso_target_url=self.setting('IDP_SSO_TARGET_URL')
        )
        return url

    def get_user_details(self, response):
        log.error('saml get_user_details')
        details = {'name_id': self.saml_response.name_id}

        attributes = self.setting('EXTRA_ATTRIBUTES')
        for name, attr in attributes:
            details[name] = (self.saml_response.get_assertion_attribute_value(attr) or [None])[0]

        return details

    def get_user_id(self, details, response):
        log.error('saml get_user_id')
        log.error(details)
        return details['name_id']

    def auth_complete(self, *args, **kwargs):
        log.error('saml auth_complete')
        uri = urlparse(self.strategy.build_absolute_uri())
        request_info = {
            'server_name': uri.hostname,
            'path_info': uri.path,
            'https': 'on' if uri.scheme == 'https' else 'off',
            'script_name': '',
        }
        if uri.port:
            request_info['server_port'] = uri.port

        response = self.strategy.request_data()

        self.saml_response = OneLogin_Saml2_Response(
            request_info,
            response.get('SAMLResponse'),
            self.setting('IDP_CERT_FINGERPRINT'),
            issuer=self.setting('ISSUER')
        )

        if not self.saml_response.is_valid():
            raise SAMLVerificationFailure('SAML response signature invalid')

        kwargs.update({
            'response': response,
            'backend': self,
        })

        return self.strategy.authenticate(*args, **kwargs)

class EdveraSamlProvider(provider.BaseProvider):
    BACKEND_CLASS = SAMLBaseAuth
    ICON_CLASS = None
    NAME = 'Saml'
    SETTINGS = {
    }

    @classmethod
    def get_email(cls, provider_details):
        return provider_details.get('email')

    @classmethod
    def get_name(cls, provider_details):
        return provider_details.get('fullname')