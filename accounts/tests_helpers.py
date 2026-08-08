"""Shared fixtures for the accounts tests."""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

#: The school's own coordinates, so a test punch is inside the geofence.
ESKOLA = {'latitude': '-8.552336', 'longitude': '125.541603'}


def punch_photo(name='punch.jpg'):
    buffer = BytesIO()
    Image.new('RGB', (8, 8)).save(buffer, format='JPEG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


def punch_evidence(**kwargs):
    """The payload a punch needs: a photo and where the device was."""
    return {'foto': punch_photo(), **ESKOLA, **kwargs}
