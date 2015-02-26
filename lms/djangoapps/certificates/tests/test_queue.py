# -*- coding: utf-8 -*-
"""TODO """
from contextlib import contextmanager
import json
from mock import patch

from django.test import TestCase
from django.test.utils import override_settings

from opaque_keys.edx.locator import CourseLocator

# TODO: why this is so bad :)
from capa.xqueue_interface import XQueueInterface

from certificates.queue import XQueueCertInterface
from certificates.models import ExampleCertificateSet, ExampleCertificate


@override_settings(CERT_QUEUE='certificates')
class XQueueCertInterfaceTest(TestCase):
    """TODO """

    COURSE_KEY = CourseLocator(org='test', course='test', run='test')

    TEMPLATE = 'test.pdf'
    DESCRIPTION = 'test'
    ERROR_MSG = 'Kaboom!'

    def setUp(self):
        super(XQueueCertInterfaceTest, self).setUp()
        self.xqueue = XQueueCertInterface()

    def test_add_example_cert(self):
        cert = self._create_example_cert()
        with self._mock_xqueue() as mock_send:
            self.xqueue.add_example_cert(cert)

        # Verify that the correct payload was sent to the XQueue
        self._assert_queue_task(mock_send, cert)

        # Verify the certificate status
        self.assertEqual(cert.status, ExampleCertificate.STATUS_STARTED)

    def test_add_example_cert_error(self):
        cert = self._create_example_cert()
        with self._mock_xqueue(success=False):
            self.xqueue.add_example_cert(cert)

        # Verify the error status of the certificate
        self.assertEqual(cert.status, ExampleCertificate.STATUS_ERROR)
        self.assertIn(self.ERROR_MSG, cert.error_reason)

    def _create_example_cert(self):
        """TODO """
        cert_set = ExampleCertificateSet.objects.create(course_key=self.COURSE_KEY)
        return ExampleCertificate.objects.create(
            example_cert_set=cert_set,
            description=self.DESCRIPTION,
            template=self.TEMPLATE
        )

    @contextmanager
    def _mock_xqueue(self, success=True):
        """TODO """
        with patch.object(XQueueInterface, 'send_to_queue') as mock_send:
            mock_send.return_value = (0, None) if success else (1, self.ERROR_MSG)
            yield mock_send

    def _assert_queue_task(self, mock_send, cert):
        """TODO """
        expected_header = json.dumps({
            'lms_key': cert.key,
            'lms_callback_url': 'https://edx.org/update_example_certificate',
            'queue_name': 'certificates'
        })

        expected_body = json.dumps({
            'action': 'create',
            'username': 'example_cert_test_user',
            'name': u'John Doë',
            'course_id': unicode(self.COURSE_KEY),
            'template_pdf': 'test.pdf'
        })

        mock_send.assert_called_once_with(
            header=expected_header,
            body=expected_body
        )
