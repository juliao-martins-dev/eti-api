"""Distance helpers for the location evidence attached to every punch."""

from math import asin, cos, radians, sin, sqrt

from django.conf import settings

#: Mean radius of the Earth, in metres.
RAIU_MUNDU = 6_371_000


def distansia_metru(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points, in metres (haversine)."""
    lat1, lon1, lat2, lon2 = map(radians, (float(lat1), float(lon1), float(lat2), float(lon2)))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * RAIU_MUNDU * asin(sqrt(a))


def distansia_husi_eskola(latitude, longitude):
    """
    Distance in metres between a punch and the school, or None when the school
    coordinates are not configured.
    """
    lat = getattr(settings, 'ESKOLA_LATITUDE', None)
    lon = getattr(settings, 'ESKOLA_LONGITUDE', None)
    if lat is None or lon is None:
        return None
    return distansia_metru(latitude, longitude, lat, lon)


def iha_eskola(latitude, longitude):
    """
    Whether a punch falls inside the school's radius. Returns None when there
    is nothing to compare against, so an unconfigured school never marks every
    punch as suspicious.
    """
    distansia = distansia_husi_eskola(latitude, longitude)
    if distansia is None:
        return None
    return distansia <= settings.ESKOLA_RAIU_METRU
