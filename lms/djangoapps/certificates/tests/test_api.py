"""
Tests for the certificates api and helper function.
"""
from contextlib import contextmanager
import ddt

from django.test import TestCase, RequestFactory
from django.test.utils import override_settings
from mock import patch, Mock

from opaque_keys.edx.locator import CourseLocator
from xmodule.modulestore.tests.factories import CourseFactory
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from student.models import CourseEnrollment
from student.tests.factories import UserFactory
from course_modes.tests.factories import CourseModeFactory
from config_models.models import cache

from certificates import api as certs_api
from certificates.models import (
    CertificateStatuses,
    CertificateGenerationConfiguration,
    ExampleCertificate
)
from certificates.queue import XQueueCertInterface
from certificates.tests.factories import GeneratedCertificateFactory


class CertificateDownloadableStatusTests(ModuleStoreTestCase):
    """
    Tests for the certificate_downloadable_status helper function
    """

    def setUp(self):
        super(CertificateDownloadableStatusTests, self).setUp()

        self.student = UserFactory()
        self.student_no_cert = UserFactory()
        self.course = CourseFactory.create(
            org='edx',
            number='verified',
            display_name='Verified Course'
        )

        self.request_factory = RequestFactory()

    def test_user_cert_status_with_generating(self):
        """
        in case of certificate with error means means is_generating is True and is_downloadable is False
        """
        GeneratedCertificateFactory.create(
            user=self.student,
            course_id=self.course.id,
            status=CertificateStatuses.generating,
            mode='verified'
        )

        self.assertEqual(
            certs_api.certificate_downloadable_status(self.student, self.course.id),
            {
                'is_downloadable': False,
                'is_generating': True,
                'download_url': None
            }
        )

    def test_user_cert_status_with_error(self):
        """
        in case of certificate with error means means is_generating is True and is_downloadable is False
        """

        GeneratedCertificateFactory.create(
            user=self.student,
            course_id=self.course.id,
            status=CertificateStatuses.error,
            mode='verified'
        )

        self.assertEqual(
            certs_api.certificate_downloadable_status(self.student, self.course.id),
            {
                'is_downloadable': False,
                'is_generating': True,
                'download_url': None
            }
        )

    def test_user_with_out_cert(self):
        """
        in case of no certificate means is_generating is False and is_downloadable is False
        """
        self.assertEqual(
            certs_api.certificate_downloadable_status(self.student_no_cert, self.course.id),
            {
                'is_downloadable': False,
                'is_generating': False,
                'download_url': None
            }
        )

    def test_user_with_downloadable_cert(self):
        """
        in case of downloadable certificate means is_generating is False and is_downloadable is True
        download_url has cert link
        """

        GeneratedCertificateFactory.create(
            user=self.student,
            course_id=self.course.id,
            status=CertificateStatuses.downloadable,
            mode='verified',
            download_url='www.google.com'
        )

        self.assertEqual(
            certs_api.certificate_downloadable_status(self.student, self.course.id),
            {
                'is_downloadable': True,
                'is_generating': False,
                'download_url': 'www.google.com'
            }
        )


class GenerateUserCertificatesTest(ModuleStoreTestCase):
    """
    Tests for the generate_user_certificates helper function
    """

    def setUp(self):
        super(GenerateUserCertificatesTest, self).setUp()

        self.student = UserFactory()
        self.student_no_cert = UserFactory()
        self.course = CourseFactory.create(
            org='edx',
            number='verified',
            display_name='Verified Course',
            grade_cutoffs={'cutoff': 0.75, 'Pass': 0.5}
        )
        self.enrollment = CourseEnrollment.enroll(self.student, self.course.id, mode='honor')
        self.request_factory = RequestFactory()

    @override_settings(CERT_QUEUE='certificates')
    @patch('courseware.grades.grade', Mock(return_value={'grade': 'Pass', 'percent': 0.75}))
    def test_new_cert_requests_into_xqueue_returns_generating(self):
        """
        mocking grade.grade and returns a summary with passing score.
        new requests saves into xqueue and returns the status
        """
        with patch('capa.xqueue_interface.XQueueInterface.send_to_queue') as mock_send_to_queue:
            mock_send_to_queue.return_value = (0, "Successfully queued")
            result = certs_api.generate_user_certificates(self.student, self.course)
            self.assertEqual(result, 'generating')


@ddt.ddt
class CertificateGenerationEnabledTest(TestCase):
    """TODO """

    COURSE_KEY = CourseLocator(org='test', course='test', run='test')

    def setUp(self):
        super(CertificateGenerationEnabledTest, self).setUp()
        # TODO -- explain this
        cache.clear()

    @ddt.data(
        (None, None, False),
        (False, None, False),
        (False, True, False),
        (True, None, False),
        (True, False, False),
        (True, True, True)
    )
    @ddt.unpack
    def test_cert_generation_enabled(self, is_feature_enabled, is_course_enabled, expect_enabled):
        if is_feature_enabled is not None:
            CertificateGenerationConfiguration.objects.create(enabled=is_feature_enabled)

        if is_course_enabled is not None:
            certs_api.cert_generation_enabled_for_course(
                self.COURSE_KEY, is_enabled=is_course_enabled
            )

        self._assert_enabled_for_course(self.COURSE_KEY, expect_enabled)

    def test_latest_setting_used(self):
        # Enable the feature
        CertificateGenerationConfiguration.objects.create(enabled=True)

        # Enable for the course
        certs_api.cert_generation_enabled_for_course(self.COURSE_KEY, is_enabled=True)
        self._assert_enabled_for_course(self.COURSE_KEY, True)

        # Disable for the course
        certs_api.cert_generation_enabled_for_course(self.COURSE_KEY, is_enabled=False)
        self._assert_enabled_for_course(self.COURSE_KEY, False)

    def _assert_enabled_for_course(self, course_key, expect_enabled):
        actual_enabled = certs_api.cert_generation_enabled_for_course(self.COURSE_KEY)
        self.assertEqual(expect_enabled, actual_enabled)


class GenerateExampleCertificatesTest(TestCase):
    """TODO """

    COURSE_KEY = CourseLocator(org='test', course='test', run='test')

    def setUp(self):
        super(GenerateExampleCertificatesTest, self).setUp()

    def test_generate_example_certs(self):
        # Generate certificates for the course
        with self._mock_xqueue() as mock_queue:
            certs_api.generate_example_certificates(self.COURSE_KEY)

        # Verify that the appropriate certs were added to the queue
        self._assert_certs_in_queue(mock_queue, 1)

        # Verify that the certificate status is "started"
        self._assert_cert_status({
            'description': 'honor',
            'status': 'started'
        })

    def test_generate_example_certs_with_verified_mode(self):
        # Create verified and honor modes for the course
        CourseModeFactory(course_id=self.COURSE_KEY, mode_slug='honor')
        CourseModeFactory(course_id=self.COURSE_KEY, mode_slug='verified')

        # Generate certificates for the course
        with self._mock_xqueue() as mock_queue:
            certs_api.generate_example_certificates(self.COURSE_KEY)

        # Verify that the appropriate certs were added to the queue
        self._assert_certs_in_queue(mock_queue, 2)

        # Verify that the certificate status is "started"
        self._assert_cert_status(
            {
                'description': 'verified',
                'status': 'started'
            },
            {
                'description': 'honor',
                'status': 'started'
            }
        )

    @contextmanager
    def _mock_xqueue(self):
        """TODO """
        with patch.object(XQueueCertInterface, 'add_example_cert') as mock_queue:
            yield mock_queue

    def _assert_certs_in_queue(self, mock_queue, expected_num):
        """TODO """
        certs_in_queue = [call_args[0] for (call_args, __) in mock_queue.call_args_list]
        self.assertEqual(len(certs_in_queue), expected_num)
        for cert in certs_in_queue:
            self.assertTrue(isinstance(cert, ExampleCertificate))

    def _assert_cert_status(self, *expected_statuses):
        actual_status = certs_api.example_certificates_status(self.COURSE_KEY)
        self.assertEqual(list(expected_statuses), actual_status)
