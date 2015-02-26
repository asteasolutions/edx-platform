# -*- coding: utf-8 -*-
"""
Certificates are created for a student and an offering of a course.

When a certificate is generated, a unique ID is generated so that
the certificate can be verified later. The ID is a UUID4, so that
it can't be easily guessed and so that it is unique.

Certificates are generated in batches by a cron job, when a
certificate is available for download the GeneratedCertificate
table is updated with information that will be displayed
on the course overview page.


State diagram:

[deleted,error,unavailable] [error,downloadable]
            +                +             +
            |                |             |
            |                |             |
         add_cert       regen_cert     del_cert
            |                |             |
            v                v             v
       [generating]    [regenerating]  [deleting]
            +                +             +
            |                |             |
       certificate      certificate    certificate
         created       removed,created   deleted
            +----------------+-------------+------->[error]
            |                |             |
            |                |             |
            v                v             v
      [downloadable]   [downloadable]  [deleted]


Eligibility:

    Students are eligible for a certificate if they pass the course
    with the following exceptions:

       If the student has allow_certificate set to False in the student profile
       he will never be issued a certificate.

       If the user and course is present in the certificate whitelist table
       then the student will be issued a certificate regardless of his grade,
       unless he has allow_certificate set to False.
"""
from datetime import datetime
import uuid

from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from model_utils import Choices
from model_utils.models import TimeStampedModel
from config_models.models import ConfigurationModel
from xmodule_django.models import CourseKeyField, NoneToEmptyManager
from util.milestones_helpers import fulfill_course_milestone
from course_modes.models import CourseMode


class CertificateStatuses(object):
    deleted = 'deleted'
    deleting = 'deleting'
    downloadable = 'downloadable'
    error = 'error'
    generating = 'generating'
    notpassing = 'notpassing'
    regenerating = 'regenerating'
    restricted = 'restricted'
    unavailable = 'unavailable'


class CertificateWhitelist(models.Model):
    """
    Tracks students who are whitelisted, all users
    in this table will always qualify for a certificate
    regardless of their grade unless they are on the
    embargoed country restriction list
    (allow_certificate set to False in userprofile).
    """

    objects = NoneToEmptyManager()

    user = models.ForeignKey(User)
    course_id = CourseKeyField(max_length=255, blank=True, default=None)
    whitelist = models.BooleanField(default=0)


class GeneratedCertificate(models.Model):

    MODES = Choices('verified', 'honor', 'audit')

    user = models.ForeignKey(User)
    course_id = CourseKeyField(max_length=255, blank=True, default=None)
    verify_uuid = models.CharField(max_length=32, blank=True, default='')
    download_uuid = models.CharField(max_length=32, blank=True, default='')
    download_url = models.CharField(max_length=128, blank=True, default='')
    grade = models.CharField(max_length=5, blank=True, default='')
    key = models.CharField(max_length=32, blank=True, default='')
    distinction = models.BooleanField(default=False)
    status = models.CharField(max_length=32, default='unavailable')
    mode = models.CharField(max_length=32, choices=MODES, default=MODES.honor)
    name = models.CharField(blank=True, max_length=255)
    created_date = models.DateTimeField(
        auto_now_add=True, default=datetime.now)
    modified_date = models.DateTimeField(
        auto_now=True, default=datetime.now)
    error_reason = models.CharField(max_length=512, blank=True, default='')

    class Meta:
        unique_together = (('user', 'course_id'),)

    @classmethod
    def certificate_for_student(cls, student, course_id):
        """
        This returns the certificate for a student for a particular course
        or None if no such certificate exits.
        """
        try:
            return cls.objects.get(user=student, course_id=course_id)
        except cls.DoesNotExist:
            pass

        return None


@receiver(post_save, sender=GeneratedCertificate)
def handle_post_cert_generated(sender, instance, **kwargs):  # pylint: disable=no-self-argument, unused-argument
    """
    Handles post_save signal of GeneratedCertificate, and mark user collected
    course milestone entry if user has passed the course
    or certificate status is 'generating'.
    """
    if settings.FEATURES.get('ENABLE_PREREQUISITE_COURSES') and instance.status == CertificateStatuses.generating:
        fulfill_course_milestone(instance.course_id, instance.user)


def certificate_status_for_student(student, course_id):
    '''
    This returns a dictionary with a key for status, and other information.
    The status is one of the following:

    unavailable  - No entry for this student--if they are actually in
                   the course, they probably have not been graded for
                   certificate generation yet.
    generating   - A request has been made to generate a certificate,
                   but it has not been generated yet.
    regenerating - A request has been made to regenerate a certificate,
                   but it has not been generated yet.
    deleting     - A request has been made to delete a certificate.

    deleted      - The certificate has been deleted.
    downloadable - The certificate is available for download.
    notpassing   - The student was graded but is not passing
    restricted   - The student is on the restricted embargo list and
                   should not be issued a certificate. This will
                   be set if allow_certificate is set to False in
                   the userprofile table

    If the status is "downloadable", the dictionary also contains
    "download_url".

    If the student has been graded, the dictionary also contains their
    grade for the course with the key "grade".
    '''

    try:
        generated_certificate = GeneratedCertificate.objects.get(
            user=student, course_id=course_id)
        d = {'status': generated_certificate.status,
             'mode': generated_certificate.mode}
        if generated_certificate.grade:
            d['grade'] = generated_certificate.grade
        if generated_certificate.status == CertificateStatuses.downloadable:
            d['download_url'] = generated_certificate.download_url

        return d
    except GeneratedCertificate.DoesNotExist:
        pass
    return {'status': CertificateStatuses.unavailable, 'mode': GeneratedCertificate.MODES.honor}


class ExampleCertificateSet(TimeStampedModel):
    """TODO """

    course_key = CourseKeyField(max_length=255, db_index=True)

    class Meta:
        get_latest_by = 'created'

    @classmethod
    @transaction.commit_on_success
    def create_example_set(cls, course_key):
        """TODO """
        cert_set = cls.objects.create(course_key=course_key)

        ExampleCertificate.objects.bulk_create([
            ExampleCertificate(
                example_cert_set=cert_set,
                description=mode.slug,
                template=cls._template_for_mode(mode.slug, course_key)
            )
            for mode in CourseMode.modes_for_course(course_key)
        ])

        return cert_set

    @classmethod
    def latest_status(cls, course_key):
        """TODO """
        # Retrieve the latest cert statuses and errors
        # Returns a list
        try:
            latest = cls.objects.latest()
        except cls.DoesNotExist:
            return None

        queryset = ExampleCertificate.objects.filter(example_cert_set=latest).order_by('-created')
        return [cert.status_dict for cert in queryset]

    def __iter__(self):
        """TODO """
        queryset = (ExampleCertificate.objects ).select_related('example_cert_set').filter(example_cert_set=self)
        for cert in queryset:
            yield cert

    @staticmethod
    def _template_for_mode(mode_slug, course_key):
        """TODO """
        return (
            u"certificate-template-{key.org}-{key.course}-verified.pdf".format(key=course_key)
            if mode_slug == 'verified'
            else u"certificate-template-{key.org}-{key.course}.pdf".format(key=course_key)
        )

class ExampleCertificate(TimeStampedModel):
    """TODO """

    example_cert_set = models.ForeignKey(ExampleCertificateSet)
    description = models.CharField(max_length=255)

    # Statuses
    STATUS_STARTED = 'started'
    STATUS_SUCCESS = 'success'
    STATUS_ERROR = 'error'

    # Default values
    EXAMPLE_USERNAME = u'example_cert_test_user'
    EXAMPLE_FULL_NAME = u'John Doë'

    # Inputs
    key = models.CharField(
        max_length=255,
        default=(lambda: uuid.uuid4().hex),
        db_index=True
    )
    username = models.CharField(max_length=255, default=EXAMPLE_USERNAME)
    full_name = models.CharField(max_length=255, default=EXAMPLE_FULL_NAME)
    template = models.CharField(max_length=255)
    grade = models.CharField(max_length=255)

    # Outputs
    status = models.CharField(max_length=255, default=STATUS_STARTED)
    error_reason = models.TextField(null=True, default=None)
    download_url = models.CharField(max_length=255, null=True, default=None)

    def update_status(self, status, error_reason=None, download_url=None):
        """TODO """
        if status not in [self.STATUS_SUCCESS, self.STATUS_ERROR]:
            raise ValueError('TODO')

        self.status = status

        if status == self.STATUS_ERROR and error_reason:
            self.error_reason = error_reason

        if status == self.STATUS_SUCCESS and download_url:
            self.download_url = download_url

        self.save()

    @property
    def status_dict(self):
        """TODO """
        return {
            'description': self.description,
            'status': self.status,
            'error_reason': self.error_reason,
            'download_url': self.download_url
        }


    @property
    def course_key(self):
        """TODO """
        return self.example_cert_set.course_key


class CertificateGenerationCourseSetting(TimeStampedModel):
    """TODO """

    course_key = CourseKeyField(max_length=255)
    enabled = models.BooleanField(default=False)

    class Meta:
        get_latest_by = 'created'

    @classmethod
    def is_enabled_for_course(cls, course_key):
        """TODO """
        try:
            latest = cls.objects.latest()
        except cls.DoesNotExist:
            return False
        else:
            return latest.enabled

    @classmethod
    def set_enabled_for_course(cls, course_key, is_enabled):
        """TODO """
        CertificateGenerationCourseSetting.objects.create(
            course_key=course_key,
            enabled=is_enabled
        )


class CertificateGenerationConfiguration(ConfigurationModel):
    """Configure certificate generation.

    TODO: more description here.

    """
    pass
