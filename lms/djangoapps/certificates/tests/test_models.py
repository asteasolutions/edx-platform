"""TODO """
from django.test import TestCase
from certificates.models import ExampleCertificate


class ExampleCertificateTest(TestCase):
    """TODO """

    def setUp(self):
        super(ExampleCertificateTest, self).setUp()
        self.cert = ExampleCertificate.objects.create(
            template='test.pdf',
        )

    def test_update_status_success(self):
        self.cert.update_status(
            ExampleCertificate.STATUS_SUCCESS,
            download_url='http://www.example.com'
        )
        self.assertEqual(
            self.cert.status_dict,
            {
                'TODO': 'test'
            }
        )

    def test_update_status_error(self):
        self.cert.update_status(
            ExampleCertificate.STATUS_ERROR,
            error_reason='http://www.example.com'
        )
        self.assertEqual(
            self.cert.status_dict,
            {
                'TODO': 'test'
            }
        )

    def test_update_status_invalid(self):
        # TODO
        with self.assertRaises(ValueError):
            self.cert.update_status('invalid')
