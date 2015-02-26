"""TODO """
import json
import ddt

from django.test import TestCase
from django.core.urlresolvers import reverse

from opaque_keys.edx.locator import CourseLocator

from certificates.models import ExampleCertificateSet, ExampleCertificate


@ddt.ddt
class UpdateExampleCertificateViewTest(TestCase):
    """TODO """

    COURSE_KEY = CourseLocator(org='test', course='test', run='test')

    DESCRIPTION = 'test'
    TEMPLATE = 'test.pdf'
    DOWNLOAD_URL = 'http://www.example.com'
    ERROR_REASON = 'Kaboom!'

    def setUp(self):
        super(UpdateExampleCertificateViewTest, self).setUp()
        self.cert_set = ExampleCertificateSet.objects.create(course_key=self.COURSE_KEY)
        self.cert = ExampleCertificate.objects.create(
            example_cert_set=self.cert_set,
            description=self.DESCRIPTION,
            template=self.TEMPLATE,
        )
        self.url = reverse('certificates.views.update_example_certificate')

    def test_update_example_certificate_success(self):
        response = self._post_to_view(key=self.cert.key, download_url=self.DOWNLOAD_URL)
        self._assert_response(response)

        self.cert = ExampleCertificate.objects.get()
        self.assertEqual(self.cert.status, ExampleCertificate.STATUS_SUCCESS)
        self.assertEqual(self.cert.download_url, self.DOWNLOAD_URL)

    def test_update_example_certificate_invalid_key(self):
        response = self._post_to_view(key='invalid', download_url=self.DOWNLOAD_URL)
        self.assertEqual(response.status_code, 404)

    def test_update_example_certificate_error(self):
        response = self._post_to_view(key=self.cert.key, error_reason=self.ERROR_REASON)
        self._assert_response(response)

        self.cert = ExampleCertificate.objects.get()
        self.assertEqual(self.cert.status, ExampleCertificate.STATUS_ERROR)
        self.assertEqual(self.cert.error_reason, self.ERROR_REASON)

    @ddt.data('xqueue_header', 'xqueue_body')
    def test_update_example_certificate_invalid_params(self, missing_param):
        payload = {
            'xqueue_header': json.dumps({
                'lms_key': self.cert.key
            }),
            'xqueue_body': json.dumps({
                'url': self.DOWNLOAD_URL
            })
        }
        del payload[missing_param]

        response = self.client.post(self.url, data=payload)
        self.assertEqual(response.status_code, 400)

    def test_update_example_certificate_missing_download_url(self):
        payload = {
            'xqueue_header': json.dumps({
                'lms_key': self.cert.key
            }),
            'xqueue_body': json.dumps({})
        }
        response = self.client.post(self.url, data=payload)
        self.assertEqual(response.status_code, 400)

    def test_update_example_cetificate_non_json_param(self):
        payload = {
            'xqueue_header': '{/invalid',
            'xqueue_body': '{/invalid'
        }
        response = self.client.post(self.url, data=payload)
        self.assertEqual(response.status_code, 400)

    def test_unsupported_http_method(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def _post_to_view(self, key, download_url=None, error_reason=None):
        """TODO """
        header = { 'lms_key': key }
        body = {}

        if download_url is not None:
            body['url'] = download_url

        if error_reason is not None:
            body['error'] = 'error'
            body['error_reason'] = self.ERROR_REASON

        payload = {
            'xqueue_header': json.dumps(header),
            'xqueue_body': json.dumps(body)
        }
        return self.client.post(self.url, data=payload)

    def _assert_response(self, response):
        """TODO """
        content = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(content['return_code'], 0)
