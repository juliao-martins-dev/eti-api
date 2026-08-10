import tempfile
from datetime import date, datetime, time
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from .geo import distansia_metru
from .models import ListaPrezensa, Marka, Prezensa, Sesaun, Tipu

User = get_user_model()

MEDIA_TEMP = override_settings(MEDIA_ROOT=tempfile.mkdtemp())

# The school, and a point far enough away to fall outside its radius.
ESKOLA = {'latitude': '-8.552336', 'longitude': '125.541603'}
DOOK = {'latitude': '-8.500000', 'longitude': '125.600000'}


def foto(name='punch.jpg'):
    buffer = BytesIO()
    Image.new('RGB', (8, 8)).save(buffer, format='JPEG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


def evidensia(**kwargs):
    """The payload of a punch: photo + where the device was."""
    return {'foto': foto(), **ESKOLA, **kwargs}


@MEDIA_TEMP
class PrezensaTests(TestCase):
    def setUp(self):
        self.profesor = User.objects.create_user(
            email='martinho@eti-dili.tl',
            numeru_id=6,
            password='x',
            naran_kompletu='Martinho Martins',
            kargu='Chefe Dep. TLP',
        )

    def prezensa(self, dia=date(2026, 2, 18)):  # Quarta-feira
        return Prezensa.objects.ba_loron(self.profesor, dia)

    def test_ba_loron_creates_sheet_and_row_once(self):
        prezensa = self.prezensa()
        self.assertEqual(prezensa.lista.fulan, 2)
        self.assertEqual(prezensa.lista.tinan, 2026)
        self.assertEqual(prezensa.lista.kargu, 'Chefe Dep. TLP')
        self.assertEqual(prezensa.loron, 'Quarta-feira')

        self.assertEqual(self.prezensa().pk, prezensa.pk)
        self.assertEqual(ListaPrezensa.objects.count(), 1)
        self.assertEqual(Prezensa.objects.count(), 1)

    def test_checkin_and_out_fill_the_session_of_the_punch(self):
        prezensa = self.prezensa()
        prezensa.checkin(oras=time(8, 3), **evidensia())
        prezensa.checkout(oras=time(12, 1), **evidensia())
        prezensa.checkin(oras=time(13, 35), **evidensia())
        prezensa.checkout(oras=time(17, 32), **evidensia())

        prezensa.refresh_from_db()
        self.assertEqual(prezensa.oras_dader_tama, time(8, 3))
        self.assertEqual(prezensa.oras_dader_fila, time(12, 1))
        self.assertEqual(prezensa.oras_lorokraik_tama, time(13, 35))
        self.assertEqual(prezensa.oras_lorokraik_fila, time(17, 32))
        self.assertEqual(prezensa.marka.count(), 4)
        self.assertEqual(prezensa.status, Prezensa.Status.PRESENT)

    def test_punch_keeps_photo_and_location_as_evidence(self):
        marka = self.prezensa().checkin(oras=time(8, 0), **evidensia(presizaun=12.5))

        self.assertEqual(marka.sesaun, Sesaun.DADER)
        self.assertEqual(marka.tipu, Tipu.TAMA)
        self.assertTrue(marka.foto.name)
        self.assertEqual(str(marka.latitude), ESKOLA['latitude'])
        self.assertEqual(marka.presizaun, 12.5)
        self.assertIsNotNone(marka.rejistu_iha)

    def test_punch_at_the_school_is_inside_the_radius(self):
        marka = self.prezensa().checkin(oras=time(8, 0), **evidensia())
        self.assertTrue(marka.iha_eskola)
        self.assertLess(marka.distansia_metru, 1)

    @override_settings(ESKOLA_OBRIGA_FATIN=True)
    def test_punch_far_from_the_school_is_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            self.prezensa().checkin(oras=time(8, 0), foto=foto(), **DOOK)

        self.assertEqual(ctx.exception.code, 'dook_husi_eskola')
        self.assertEqual(Marka.objects.count(), 0)

    def test_punch_just_inside_the_radius_is_accepted(self):
        # ~0.0007 degrees of latitude is about 78 m -- inside the 100 m radius.
        marka = self.prezensa().checkin(
            oras=time(8, 0),
            foto=foto(),
            latitude='-8.551636',
            longitude='125.541603',
        )
        self.assertTrue(marka.iha_eskola)
        self.assertLess(marka.distansia_metru, 100)

    @override_settings(ESKOLA_OBRIGA_FATIN=False)
    def test_out_of_radius_punch_is_recorded_when_enforcement_is_off(self):
        marka = self.prezensa().checkin(oras=time(8, 0), foto=foto(), **DOOK)

        self.assertFalse(marka.iha_eskola)
        self.assertGreater(marka.distansia_metru, 100)
        self.assertEqual(Marka.objects.count(), 1)

    @override_settings(ESKOLA_LATITUDE=None, ESKOLA_LONGITUDE=None)
    def test_unconfigured_school_never_blocks_a_punch(self):
        marka = self.prezensa().checkin(oras=time(8, 0), foto=foto(), **DOOK)

        self.assertIsNone(marka.iha_eskola)
        self.assertIsNone(marka.distansia_metru)

    def test_second_checkin_of_the_same_session_is_rejected(self):
        prezensa = self.prezensa()
        prezensa.checkin(oras=time(8, 3), **evidensia())
        with self.assertRaises(ValidationError) as ctx:
            prezensa.checkin(oras=time(9, 0), **evidensia())
        self.assertEqual(ctx.exception.code, 'duplicate')
        self.assertEqual(prezensa.marka.count(), 1)

    def test_checkout_without_checkin_is_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            self.prezensa().checkout(oras=time(12, 0), **evidensia())
        self.assertEqual(ctx.exception.code, 'no_checkin')

    def test_saturday_has_no_afternoon_session(self):
        sabadu = self.prezensa(date(2026, 2, 21))
        self.assertTrue(sabadu.sabadu)
        sabadu.checkin(oras=time(8, 0), **evidensia())
        sabadu.checkout(oras=time(12, 0), **evidensia())
        with self.assertRaises(ValidationError) as ctx:
            sabadu.checkin(oras=time(14, 0), **evidensia())
        self.assertEqual(ctx.exception.code, 'no_session')


@MEDIA_TEMP
class IstoriaTests(APITestCase):
    """One month of the teacher's own sheet: /api/prezensa/istoria/."""

    def setUp(self):
        self.profesor = User.objects.create_user(
            email='martinho@eti-dili.tl',
            numeru_id=6,
            password='x',
            naran_kompletu='Martinho Martins',
        )
        self.client.force_authenticate(self.profesor)

    def marka(self, dia, oras=time(8, 3)):
        return Prezensa.objects.ba_loron(self.profesor, dia).checkin(
            oras=oras, **evidensia()
        )

    def istoria(self, **params):
        return self.client.get('/api/prezensa/istoria/', params)

    def test_month_lists_every_working_day_marked_or_not(self):
        self.marka(date(2026, 2, 18))

        body = self.istoria(fulan=2, tinan=2026).json()

        # February 2026 has 28 days and four Sundays -> 24 working days.
        self.assertEqual(len(body['loron']), 24)
        self.assertEqual(body['fulan_display'], 'Fevereiru')
        self.assertEqual(body['tinan'], 2026)
        self.assertNotIn(
            'Domingu', [loron['loron'] for loron in body['loron']]
        )

        marka_ona = [loron for loron in body['loron'] if loron['marka']]
        self.assertEqual(len(marka_ona), 1)
        self.assertEqual(marka_ona[0]['data'], '2026-02-18')
        self.assertEqual(marka_ona[0]['oras_dader_tama'], '08:03:00')

        # A day nobody marked still appears, empty.
        mamuk = next(l for l in body['loron'] if l['data'] == '2026-02-19')
        self.assertEqual(mamuk['marka'], [])
        self.assertIsNone(mamuk['status'])
        self.assertEqual(mamuk['loron'], 'Quinta-feira')

    def test_summary_counts_the_month(self):
        self.marka(date(2026, 2, 18), oras=time(8, 3))   # late
        self.marka(date(2026, 2, 17), oras=time(7, 55))  # on time

        rezumu = self.istoria(fulan=2, tinan=2026).json()['rezumu']
        self.assertEqual(rezumu['loron_servisu'], 24)
        self.assertEqual(rezumu['marka_ona'], 2)
        self.assertEqual(rezumu['seidauk_marka'], 22)
        self.assertEqual(rezumu['marka_total'], 2)
        self.assertEqual(rezumu['atrazadu'], 1)

    def test_days_are_grouped_into_weeks_starting_on_monday(self):
        body = self.istoria(fulan=2, tinan=2026).json()
        semana = {loron['data']: loron['semana'] for loron in body['loron']}

        # 2026-02-01 is a Sunday, so the month opens mid-week.
        self.assertEqual(semana['2026-02-02'], 2)  # Monday
        self.assertEqual(semana['2026-02-07'], 2)  # Saturday, same week
        self.assertEqual(semana['2026-02-09'], 3)  # next Monday

    def test_semana_narrows_the_answer_to_one_week(self):
        body = self.istoria(fulan=2, tinan=2026, semana=2).json()

        self.assertEqual(body['semana'], 2)
        self.assertEqual(len(body['loron']), 6)  # Monday to Saturday
        self.assertEqual(body['loron'][0]['data'], '2026-02-02')
        self.assertEqual(body['loron'][-1]['data'], '2026-02-07')

    def test_defaults_to_the_current_month(self):
        ohin = timezone.localdate()
        body = self.istoria().json()
        self.assertEqual(body['fulan'], ohin.month)
        self.assertEqual(body['tinan'], ohin.year)
        self.assertIsNone(body['semana'])

    def test_another_teachers_month_is_never_included(self):
        seluk = User.objects.create_user(
            email='joao@eti-dili.tl',
            numeru_id=1,
            password='x',
            naran_kompletu='João Gaio',
        )
        Prezensa.objects.ba_loron(seluk, date(2026, 2, 18)).checkin(
            oras=time(8, 0), **evidensia()
        )

        body = self.istoria(fulan=2, tinan=2026).json()
        self.assertEqual(body['rezumu']['marka_ona'], 0)

    def test_a_broken_period_is_rejected(self):
        for params in ({'fulan': 13}, {'fulan': 'agostu'}, {'semana': 9}):
            response = self.istoria(**params)
            self.assertEqual(response.status_code, 400, params)
            self.assertEqual(response.json()['code'], 'invalid_period')

    def test_sheet_header_carries_naran_and_kargu(self):
        body = self.istoria(fulan=2, tinan=2026).json()
        self.assertEqual(body['profesor'], 'Martinho Martins')
        self.assertIn('kargu', body)

    def test_admin_can_open_a_specific_teachers_sheet(self):
        self.marka(date(2026, 2, 18))
        diretor = User.objects.create_superuser(
            email='joao@eti-dili.tl', numeru_id=1, password='x',
            naran_kompletu='João Gaio', kargu='Diretor',
        )
        self.client.force_authenticate(diretor)

        body = self.istoria(
            fulan=2, tinan=2026, profesor=self.profesor.pk
        ).json()

        self.assertEqual(body['profesor'], 'Martinho Martins')
        marka_ona = [loron for loron in body['loron'] if loron['marka']]
        self.assertEqual(len(marka_ona), 1)
        self.assertEqual(marka_ona[0]['data'], '2026-02-18')

    def test_ordinary_teacher_cannot_open_anothers_sheet(self):
        seluk = User.objects.create_user(
            email='benedito@eti-dili.tl', numeru_id=8, password='x',
            naran_kompletu='Benedito Soares',
        )
        response = self.istoria(fulan=2, tinan=2026, profesor=seluk.pk)
        self.assertEqual(response.status_code, 403)

    def test_unknown_profesor_on_istoria_is_rejected(self):
        diretor = User.objects.create_superuser(
            email='joao@eti-dili.tl', numeru_id=1, password='x',
            naran_kompletu='João Gaio',
        )
        self.client.force_authenticate(diretor)
        response = self.istoria(fulan=2, tinan=2026, profesor=9999)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'invalid_profesor')

    def test_istoria_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.istoria().status_code, 401)


@MEDIA_TEMP
class RelatoriuOhinTests(APITestCase):
    """The administration's daily report: /api/prezensa/ohin-hotu/."""

    def setUp(self):
        self.profesor = User.objects.create_user(
            email='martinho@eti-dili.tl',
            numeru_id=6,
            password='x',
            naran_kompletu='Martinho Martins',
            kargu='Chefe Dep. TLP',
        )
        self.seluk = User.objects.create_user(
            email='benedito@eti-dili.tl',
            numeru_id=8,
            password='x',
            naran_kompletu='Benedito Soares',
            kargu='Chefe Dep. Multimedia',
        )
        self.diretor = User.objects.create_superuser(
            email='joao@eti-dili.tl',
            numeru_id=1,
            password='x',
            naran_kompletu='João Gaio',
            kargu='Diretor',
        )

    def test_report_lists_every_teacher_marked_or_not(self):
        Prezensa.objects.ba_loron(self.profesor).checkin(
            oras=time(8, 3), **evidensia()
        )
        self.client.force_authenticate(self.diretor)

        body = self.client.get('/api/prezensa/ohin-hotu/').json()

        # The director keeps a sheet like everyone else, so ADMIN accounts
        # are on the report too -- two teachers plus the director.
        self.assertEqual(body['rezumu'], {
            'total': 3, 'marka_ona': 1, 'seidauk_marka': 2,
        })

        liña = {item['profesor']['naran_kompletu']: item for item in body['profesor']}
        marka = liña['Martinho Martins']
        self.assertTrue(marka['marka_ona'])
        self.assertEqual(marka['profesor']['numeru_id'], 6)
        self.assertEqual(marka['prezensa']['oras_dader_tama'], '08:03:00')
        self.assertEqual(len(marka['prezensa']['marka']), 1)

        self.assertFalse(liña['Benedito Soares']['marka_ona'])
        self.assertIsNone(liña['Benedito Soares']['prezensa'])

        # The admin appears as a teacher who has not punched yet.
        self.assertIn('João Gaio', liña)
        self.assertFalse(liña['João Gaio']['marka_ona'])

    def test_an_ordinary_teacher_cannot_open_the_report(self):
        self.client.force_authenticate(self.profesor)
        response = self.client.get('/api/prezensa/ohin-hotu/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_open_the_report(self):
        response = self.client.get('/api/prezensa/ohin-hotu/')
        self.assertEqual(response.status_code, 401)


class GeoTests(TestCase):
    def test_distance_between_two_known_points(self):
        # One degree of latitude is ~111 km anywhere on the globe.
        metru = distansia_metru(-8.0, 125.0, -9.0, 125.0)
        self.assertAlmostEqual(metru / 1000, 111.2, delta=1)

    def test_distance_to_itself_is_zero(self):
        self.assertAlmostEqual(distansia_metru(-8.56, 125.54, -8.56, 125.54), 0)


@MEDIA_TEMP
class ClockApiTests(APITestCase):
    def setUp(self):
        self.profesor = User.objects.create_user(
            email='martinho@eti-dili.tl',
            numeru_id=6,
            password='senha-forte-123',
            naran_kompletu='Martinho Martins',
            kargu='Chefe Dep. TLP',
        )
        self.client.force_authenticate(self.profesor)
        self.oras_ohin(datetime(2026, 2, 18, 8, 3))  # Quarta-feira, dader

    def oras_ohin(self, agora):
        """
        Pin "now" for the request cycle. Without this the suite would fail on a
        Saturday afternoon, when there is no session to punch into.
        """
        agora = timezone.make_aware(agora)
        for modulu in ('attendance.models', 'attendance.serializers'):
            patcher = mock.patch(f'{modulu}.timezone')
            relojiu = patcher.start()
            relojiu.localtime.return_value = agora
            relojiu.localdate.return_value = agora.date()
            self.addCleanup(patcher.stop)

    def test_ohin_creates_todays_row(self):
        response = self.client.get('/api/prezensa/ohin/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['profesor'], 'Martinho Martins')
        self.assertTrue(response.json()['bele_checkin'])
        self.assertEqual(response.json()['marka'], [])

    def test_checkin_then_checkout(self):
        response = self.client.post('/api/prezensa/checkin/', evidensia())
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIsNotNone(body['oras_tama'])
        self.assertTrue(body['bele_checkout'])
        self.assertEqual(len(body['marka']), 1)
        self.assertTrue(body['marka'][0]['iha_eskola'])
        self.assertIn('.jpg', body['marka'][0]['foto'])

        response = self.client.post('/api/prezensa/checkin/', evidensia())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'duplicate')

        response = self.client.post('/api/prezensa/checkout/', evidensia())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNotNone(response.json()['oras_fila'])

    def test_checkin_requires_a_photo(self):
        payload = evidensia()
        del payload['foto']
        response = self.client.post('/api/prezensa/checkin/', payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('foto', response.json())

    def test_checkin_requires_coordinates(self):
        response = self.client.post('/api/prezensa/checkin/', {'foto': foto()})
        self.assertEqual(response.status_code, 400)
        self.assertIn('latitude', response.json())
        self.assertIn('longitude', response.json())

    def test_checkin_accepts_the_full_precision_a_phone_reports(self):
        response = self.client.post(
            '/api/prezensa/checkin/',
            {
                'foto': foto(),
                'latitude': '-8.5523361234567',
                'longitude': '125.5416034567891',
                'presizaun': 14.2,
            },
        )
        self.assertEqual(response.status_code, 201, response.content)

        marka = Marka.objects.get()
        self.assertEqual(str(marka.latitude), '-8.552336')
        self.assertEqual(str(marka.longitude), '125.541603')

    def test_checkin_rounds_rather_than_truncates(self):
        response = self.client.post(
            '/api/prezensa/checkin/',
            {'foto': foto(), 'latitude': '-8.5523369', 'longitude': '125.5416031'},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(str(Marka.objects.get().latitude), '-8.552337')

    def test_checkin_rejects_a_coordinate_with_too_many_whole_digits(self):
        response = self.client.post(
            '/api/prezensa/checkin/',
            {'foto': foto(), 'latitude': '1234.5', 'longitude': '125.541603'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('latitude', response.json())

    def test_checkin_rejects_impossible_coordinates(self):
        response = self.client.post(
            '/api/prezensa/checkin/',
            {'foto': foto(), 'latitude': '95.000000', 'longitude': '125.545100'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('latitude', response.json())

    def test_response_names_the_book_column_it_filled(self):
        response = self.client.post('/api/prezensa/checkin/', evidensia())
        marka = response.json()['marka_foun']

        self.assertEqual(marka['kolumna'], 'ORAS_DADER_TAMA')
        self.assertEqual(marka['oras_orariu'], '08:00:00')
        # 08:03 is after the 08:00 printed in the column header.
        self.assertTrue(marka['atrazadu'])

    def test_sesaun_targets_a_session_explicitly(self):
        response = self.client.post(
            '/api/prezensa/checkin/', evidensia(sesaun=Sesaun.DADER)
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['marka_foun']['kolumna'], 'ORAS_DADER_TAMA')

        response = self.client.post(
            '/api/prezensa/checkout/', evidensia(sesaun=Sesaun.DADER)
        )
        self.assertEqual(response.json()['marka_foun']['kolumna'], 'ORAS_DADER_FILA')

        # The morning is closed; the afternoon is still untouched.
        response = self.client.post(
            '/api/prezensa/checkin/', evidensia(sesaun=Sesaun.LOROKRAIK)
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            response.json()['marka_foun']['kolumna'], 'ORAS_LOROKRAIK_TAMA'
        )

    def test_checkout_of_a_session_never_opened_is_rejected(self):
        response = self.client.post(
            '/api/prezensa/checkout/', evidensia(sesaun=Sesaun.LOROKRAIK)
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'no_checkin')

    def test_unknown_sesaun_is_rejected(self):
        response = self.client.post(
            '/api/prezensa/checkin/', evidensia(sesaun='KALAN')
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('sesaun', response.json())

    @override_settings(ESKOLA_OBRIGA_FATIN=True)
    def test_punch_away_from_the_school_is_refused_with_the_distance(self):
        response = self.client.post(
            '/api/prezensa/checkin/', {'foto': foto(), **DOOK}
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body['code'], 'dook_husi_eskola')
        self.assertGreater(body['distansia'], 100)
        self.assertEqual(Marka.objects.count(), 0)

    def test_anonymous_cannot_punch(self):
        self.client.force_authenticate(None)
        response = self.client.post('/api/prezensa/checkin/', evidensia())
        self.assertEqual(response.status_code, 401)


@MEDIA_TEMP
class HotuTests(APITestCase):
    """The dashboard's period grid: /api/prezensa/hotu/ (plan R2)."""

    def setUp(self):
        self.diretor = User.objects.create_superuser(
            email='joao@eti-dili.tl', numeru_id=1, password='x',
            naran_kompletu='João Gaio', kargu='Diretor',
        )
        self.martinho = User.objects.create_user(
            email='martinho@eti-dili.tl', numeru_id=6, password='x',
            naran_kompletu='Martinho Martins', kargu='Chefe Dep. TLP',
        )
        self.benedito = User.objects.create_user(
            email='benedito@eti-dili.tl', numeru_id=8, password='x',
            naran_kompletu='Benedito Soares',
        )
        Prezensa.objects.ba_loron(self.martinho, date(2026, 2, 18)).checkin(
            oras=time(8, 3), **evidensia()
        )
        self.client.force_authenticate(self.diretor)

    def test_month_lists_every_teacher_on_every_working_day(self):
        body = self.client.get('/api/prezensa/hotu/?fulan=2&tinan=2026').json()

        # (2 teachers + the director, who keeps a sheet too) x 24 working days.
        self.assertEqual(len(body['profesor']), 72)
        self.assertEqual(body['fulan'], 2)
        self.assertEqual(body['tinan'], 2026)

        marka = next(
            linha for linha in body['profesor']
            if linha['data'] == '2026-02-18'
            and linha['profesor']['naran_kompletu'] == 'Martinho Martins'
        )
        self.assertTrue(marka['marka_ona'])
        self.assertEqual(marka['prezensa']['oras_dader_tama'], '08:03:00')
        self.assertEqual(len(marka['prezensa']['marka']), 1)

        mamuk = next(
            linha for linha in body['profesor']
            if linha['data'] == '2026-02-19'
            and linha['profesor']['naran_kompletu'] == 'Benedito Soares'
        )
        self.assertIsNone(mamuk['prezensa'])
        self.assertFalse(mamuk['marka_ona'])

    def test_profesor_param_narrows_to_one_teacher(self):
        body = self.client.get(
            f'/api/prezensa/hotu/?fulan=2&tinan=2026&profesor={self.martinho.pk}'
        ).json()
        self.assertEqual(len(body['profesor']), 24)
        self.assertTrue(all(
            linha['profesor']['naran_kompletu'] == 'Martinho Martins'
            for linha in body['profesor']
        ))

    def test_semana_narrows_to_one_week(self):
        body = self.client.get(
            '/api/prezensa/hotu/?fulan=2&tinan=2026&semana=2'
        ).json()
        # Week 2 of Feb 2026 is Mon 02..Sat 07 -> 6 days x 3 staff.
        self.assertEqual(len(body['profesor']), 18)

    def test_data_mode_returns_a_single_day(self):
        body = self.client.get('/api/prezensa/hotu/?data=2026-02-18').json()
        self.assertEqual(body['data'], '2026-02-18')
        self.assertEqual(body['loron'], 'Quarta-feira')
        self.assertEqual(len(body['profesor']), 3)

    def test_marka_false_omits_the_nested_punches(self):
        body = self.client.get(
            '/api/prezensa/hotu/?data=2026-02-18&marka=false'
        ).json()
        marka = next(
            linha for linha in body['profesor']
            if linha['profesor']['naran_kompletu'] == 'Martinho Martins'
        )
        self.assertNotIn('marka', marka['prezensa'])
        self.assertEqual(marka['prezensa']['oras_dader_tama'], '08:03:00')
        self.assertTrue(marka['marka_ona'])

    def test_broken_periods_are_rejected(self):
        for query in ('?fulan=13', '?data=la-loos'):
            response = self.client.get(f'/api/prezensa/hotu/{query}')
            self.assertEqual(response.status_code, 400, query)
            self.assertEqual(response.json()['code'], 'invalid_period')

    def test_an_ordinary_teacher_cannot_open_it(self):
        self.client.force_authenticate(self.martinho)
        response = self.client.get('/api/prezensa/hotu/?fulan=2&tinan=2026')
        self.assertEqual(response.status_code, 403)


@MEDIA_TEMP
class StatusTests(APITestCase):
    """Hand-written status over a range: /api/prezensa/status/ (plan R5, R6)."""

    def setUp(self):
        self.diretor = User.objects.create_superuser(
            email='joao@eti-dili.tl', numeru_id=1, password='x',
            naran_kompletu='João Gaio',
        )
        self.profesor = User.objects.create_user(
            email='martinho@eti-dili.tl', numeru_id=6, password='x',
            naran_kompletu='Martinho Martins', kargu='Chefe Dep. TLP',
        )
        self.client.force_authenticate(self.diretor)

    def rejistu(self, **override):
        payload = {
            'profesor': self.profesor.pk,
            'status': 'LEAVE',
            'husi': '2026-02-05',
            'too': '2026-02-09',
            'obs': 'Moras -- atestadu médiku',
            **override,
        }
        return self.client.post('/api/prezensa/status/', payload, format='json')

    def test_range_writes_status_and_obs_skipping_sunday(self):
        response = self.rejistu()
        self.assertEqual(response.status_code, 201, response.content)

        body = response.json()
        # Thu 5, Fri 6, Sat 7, Mon 9 -- Sunday the 8th skipped.
        self.assertEqual(body['total'], 4)
        self.assertNotIn('2026-02-08', body['loron'])

        dias = Prezensa.objects.filter(
            lista__profesor=self.profesor, status='LEAVE'
        )
        self.assertEqual(dias.count(), 4)
        self.assertTrue(all(d.obs == 'Moras -- atestadu médiku' for d in dias))

    def test_husi_after_too_is_rejected(self):
        response = self.rejistu(husi='2026-02-09', too='2026-02-05')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'invalid_period')

    def test_present_cannot_be_hand_written(self):
        response = self.rejistu(status='PRESENT')
        self.assertEqual(response.status_code, 400)
        self.assertIn('status', response.json())

    def test_unknown_profesor_is_rejected(self):
        response = self.rejistu(profesor=9999)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'invalid_profesor')

    def test_a_punched_day_blocks_the_whole_range(self):
        Prezensa.objects.ba_loron(self.profesor, date(2026, 2, 6)).checkin(
            oras=time(8, 0), **evidensia()
        )

        response = self.rejistu()
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body['code'], 'iha_marka')
        self.assertIn('2026-02-06', body['loron'])

        # Atomic: no day in the range was written, not even conflict-free ones.
        self.assertFalse(
            Prezensa.objects.filter(
                lista__profesor=self.profesor, status='LEAVE'
            ).exists()
        )

    def test_delete_returns_the_day_to_no_record(self):
        self.rejistu(husi='2026-02-05', too='2026-02-05')

        response = self.client.delete(
            '/api/prezensa/status/',
            {'profesor': self.profesor.pk, 'data': '2026-02-05'},
            format='json',
        )
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(
            Prezensa.objects.filter(
                lista__profesor=self.profesor, data=date(2026, 2, 5)
            ).exists()
        )

    def test_delete_refuses_a_punched_day(self):
        Prezensa.objects.ba_loron(self.profesor, date(2026, 2, 6)).checkin(
            oras=time(8, 0), **evidensia()
        )
        response = self.client.delete(
            '/api/prezensa/status/',
            {'profesor': self.profesor.pk, 'data': '2026-02-06'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'iha_marka')

    def test_delete_of_a_missing_day_is_404(self):
        response = self.client.delete(
            '/api/prezensa/status/',
            {'profesor': self.profesor.pk, 'data': '2026-02-05'},
            format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_an_ordinary_teacher_cannot_write_status(self):
        self.client.force_authenticate(self.profesor)
        self.assertEqual(self.rejistu().status_code, 403)


class KonfigTests(APITestCase):
    """System info panel: /api/konfig/ (plan R8)."""

    def setUp(self):
        self.profesor = User.objects.create_user(
            email='martinho@eti-dili.tl', numeru_id=6, password='x',
            naran_kompletu='Martinho Martins',
        )

    def test_returns_schedule_and_geofence_without_coordinates(self):
        self.client.force_authenticate(self.profesor)
        response = self.client.get('/api/konfig/')
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body['oras_dader_tama'], '08:00:00')
        self.assertEqual(body['oras_lorokraik_fila'], '17:30:00')
        self.assertEqual(body['limite_sesaun'], '13:00:00')
        self.assertIn('eskola_raiu_metru', body)
        self.assertIn('eskola_obriga_fatin', body)

        # The geofence centre must never be published.
        self.assertFalse(
            any('latitude' in key or 'longitude' in key for key in body)
        )

    def test_requires_authentication(self):
        self.assertEqual(self.client.get('/api/konfig/').status_code, 401)
