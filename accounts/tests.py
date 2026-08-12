import os
import tempfile
from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from .models import User

MEDIA_TEMP = override_settings(MEDIA_ROOT=tempfile.mkdtemp())

SENHA = 'senha-forte-123'
SENHA_ADMIN = 'senha-admin-456'


def foto(name='martinho.jpg'):
    buffer = BytesIO()
    Image.new('RGB', (8, 8)).save(buffer, format='JPEG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/jpeg')


@MEDIA_TEMP
class AuthTests(APITestCase):
    def setUp(self):
        self.profesor = User.objects.create_user(
            email='martinho@eti-dili.tl',
            password=SENHA,
            numeru_id=6,
            naran_kompletu='Martinho Martins',
            kargu='Chefe Dep. TLP',
            foto=foto(),
        )

    def login(self):
        return self.client.post(
            '/api/auth/login/',
            {'email': self.profesor.email, 'password': SENHA},
        )

    def autentika(self):
        """Log in and put the access token on the client."""
        access = self.login().json()['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        return access

    def test_login_returns_tokens_with_photo_and_email(self):
        response = self.login()
        self.assertEqual(response.status_code, 200, response.content)

        body = response.json()
        self.assertIn('access', body)
        self.assertIn('refresh', body)
        self.assertEqual(body['user']['email'], 'martinho@eti-dili.tl')
        self.assertEqual(body['user']['numeru_id'], 6)
        self.assertEqual(body['user']['naran_kompletu'], 'Martinho Martins')
        self.assertEqual(body['user']['kargu'], 'Chefe Dep. TLP')
        self.assertTrue(body['user']['foto'].startswith('http'))
        self.assertIn('.jpg', body['user']['foto'])

    def test_login_with_wrong_password_is_rejected(self):
        response = self.client.post(
            '/api/auth/login/',
            {'email': self.profesor.email, 'password': 'sala'},
        )
        self.assertEqual(response.status_code, 401)

    def test_access_token_authenticates_the_api(self):
        access = self.login().json()['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        response = self.client.get('/api/auth/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['email'], self.profesor.email)

    def test_patch_me_replaces_the_photo(self):
        self.autentika()
        tuan_path = self.profesor.foto.path
        tuan_name = self.profesor.foto.name

        response = self.client.patch(
            '/api/auth/me/', {'foto': foto('foun.jpg')}, format='multipart'
        )
        self.assertEqual(response.status_code, 200, response.content)

        # The whole profile comes back, pointing at the new file.
        body = response.json()
        self.assertEqual(body['email'], self.profesor.email)
        self.assertEqual(body['numeru_id'], 6)

        self.profesor.refresh_from_db()
        self.assertNotEqual(self.profesor.foto.name, tuan_name)
        self.assertIn(self.profesor.foto.name, body['foto'])
        self.assertTrue(os.path.exists(self.profesor.foto.path))
        self.assertFalse(os.path.exists(tuan_path), 'the replaced file should be gone')

    def test_a_stored_name_is_never_reused(self):
        """
        The clients always upload the same filename, and the old file is
        deleted on replacement -- which used to free the name for the *next*
        upload. A cached URL could then resolve to somebody else's photo.
        """
        self.autentika()
        seluk = User.objects.create_user(
            email='benedito@eti-dili.tl', password='x', numeru_id=8,
            naran_kompletu='Benedito Soares',
        )

        naran = {self.profesor.foto.name}
        for _ in range(3):
            self.client.patch(
                '/api/auth/me/', {'foto': foto('foto.jpg')}, format='multipart'
            )
            self.profesor.refresh_from_db()
            self.assertNotIn(self.profesor.foto.name, naran)
            naran.add(self.profesor.foto.name)

        # A second account uploading the same filename cannot land on a name
        # the first one has used.
        self.client.force_authenticate(seluk)
        self.client.patch(
            '/api/auth/me/', {'foto': foto('foto.jpg')}, format='multipart'
        )
        seluk.refresh_from_db()
        self.assertNotIn(seluk.foto.name, naran)

    def test_patch_me_ignores_every_field_but_the_photo(self):
        self.autentika()
        response = self.client.patch(
            '/api/auth/me/',
            {
                'foto': foto('foun.jpg'),
                'email': 'nakfila@eti-dili.tl',
                'naran_kompletu': 'Seluk',
                'numeru_id': 99,
                'role': 'ADMIN',
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 200)

        self.profesor.refresh_from_db()
        self.assertEqual(self.profesor.email, 'martinho@eti-dili.tl')
        self.assertEqual(self.profesor.naran_kompletu, 'Martinho Martins')
        self.assertEqual(self.profesor.numeru_id, 6)
        self.assertEqual(self.profesor.role, User.Role.PROFESSOR)

    def test_patch_me_without_a_photo_is_rejected(self):
        self.autentika()
        response = self.client.patch('/api/auth/me/', {}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('foto', response.json())

    def test_patch_me_rejects_a_file_that_is_not_an_image(self):
        self.autentika()
        response = self.client.patch(
            '/api/auth/me/',
            {'foto': SimpleUploadedFile('x.jpg', b'not an image', 'image/jpeg')},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('foto', response.json())

    def test_put_me_is_not_allowed(self):
        self.autentika()
        response = self.client.put(
            '/api/auth/me/', {'foto': foto()}, format='multipart'
        )
        self.assertEqual(response.status_code, 405)

    def test_patch_me_requires_authentication(self):
        response = self.client.patch(
            '/api/auth/me/', {'foto': foto()}, format='multipart'
        )
        self.assertEqual(response.status_code, 401)

    def test_logout_blacklists_the_refresh_token(self):
        body = self.login().json()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {body["access"]}')

        response = self.client.post('/api/auth/logout/', {'refresh': body['refresh']})
        self.assertEqual(response.status_code, 205, response.content)

        # The blacklisted token can no longer be exchanged for a new access one.
        response = self.client.post('/api/auth/refresh/', {'refresh': body['refresh']})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'token_not_valid')

    def test_logout_rejects_a_garbage_token(self):
        body = self.login().json()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {body["access"]}')

        response = self.client.post('/api/auth/logout/', {'refresh': 'lia-fuan-sala'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'token_not_valid')

    def test_logout_requires_authentication(self):
        refresh = self.login().json()['refresh']
        response = self.client.post('/api/auth/logout/', {'refresh': refresh})
        self.assertEqual(response.status_code, 401)

    def test_refresh_rotates_and_blacklists_the_old_token(self):
        body = self.login().json()

        response = self.client.post('/api/auth/refresh/', {'refresh': body['refresh']})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()['refresh'], body['refresh'])

        response = self.client.post('/api/auth/refresh/', {'refresh': body['refresh']})
        self.assertEqual(response.status_code, 401)


@MEDIA_TEMP
class ProfesorApiTests(APITestCase):
    """The dashboard roster: /api/profesor/ (plan R1, R3, R4, delete)."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='joao@eti-dili.tl', password=SENHA_ADMIN, numeru_id=1,
            naran_kompletu='João Gaio', kargu='Diretor',
        )
        self.profesor = User.objects.create_user(
            email='martinho@eti-dili.tl', password='x', numeru_id=6,
            naran_kompletu='Martinho Martins', kargu='Chefe Dep. TLP',
        )
        self.inativu = User.objects.create_user(
            email='benedito@eti-dili.tl', password='x', numeru_id=8,
            naran_kompletu='Benedito Soares', is_active=False,
        )
        self.client.force_authenticate(self.admin)

    def test_list_includes_inactive_and_excludes_admins(self):
        response = self.client.get('/api/profesor/')
        self.assertEqual(response.status_code, 200, response.content)

        naran = {row['naran_kompletu']: row for row in response.json()}
        self.assertIn('Martinho Martins', naran)
        self.assertIn('Benedito Soares', naran)
        # Admins are listed too, so the roster agrees with every report screen.
        self.assertIn('João Gaio', naran)
        self.assertEqual(naran['João Gaio']['role'], 'ADMIN')
        self.assertEqual(naran['João Gaio']['role_display'], 'Administradór')

        self.assertFalse(naran['Benedito Soares']['is_active'])
        self.assertEqual(naran['Martinho Martins']['numeru_id'], 6)
        self.assertIn('nu_kontaktu', naran['Martinho Martins'])

    def test_create_returns_the_initial_password_once(self):
        response = self.client.post('/api/profesor/', {
            'numeru_id': 20,
            'naran_kompletu': 'Ana Paula Ximenes',
            'email': 'ana@eti-dili.tl',
            'kargu': 'Profesóra Matemátika',
            'nu_kontaktu': '+670 7810 3345',
            'sexu': 'FETO',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)

        body = response.json()
        senha = body['password_inisial']
        self.assertTrue(senha)
        self.assertEqual(body['role'], 'PROFESSOR')

        foun = User.objects.get(email='ana@eti-dili.tl')
        self.assertTrue(foun.check_password(senha))
        self.assertEqual(foun.numeru_id, 20)

    def test_create_duplicate_numeru_is_a_coded_400(self):
        response = self.client.post('/api/profesor/', {
            'numeru_id': 6,
            'naran_kompletu': 'Seluk',
            'email': 'seluk@eti-dili.tl',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'duplicate_numeru')

    def test_create_duplicate_email_is_a_coded_400(self):
        response = self.client.post('/api/profesor/', {
            'numeru_id': 30,
            'naran_kompletu': 'Seluk',
            'email': 'martinho@eti-dili.tl',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'duplicate_email')

    def test_patch_updates_and_deactivates(self):
        response = self.client.patch(
            f'/api/profesor/{self.profesor.pk}/',
            {'kargu': 'Vice Diretor I', 'is_active': False},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['kargu'], 'Vice Diretor I')

        self.profesor.refresh_from_db()
        self.assertEqual(self.profesor.kargu, 'Vice Diretor I')
        self.assertFalse(self.profesor.is_active)
        # A soft toggle -- the account and its sheets still exist.
        self.assertTrue(User.objects.filter(pk=self.profesor.pk).exists())

    def test_patch_duplicate_email_between_teachers_is_refused(self):
        response = self.client.patch(
            f'/api/profesor/{self.profesor.pk}/',
            {'email': 'benedito@eti-dili.tl'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'duplicate_email')

    def test_patching_own_email_to_itself_is_fine(self):
        response = self.client.patch(
            f'/api/profesor/{self.profesor.pk}/',
            {'email': 'martinho@eti-dili.tl', 'kargu': 'GAT'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_put_is_not_allowed(self):
        self.assertEqual(
            self.client.put(
                f'/api/profesor/{self.profesor.pk}/', {}, format='json'
            ).status_code,
            405,
        )

    # -- DELETE ---------------------------------------------------------

    def hamos(self, profesor=None, **corpu):
        return self.client.delete(
            f'/api/profesor/{(profesor or self.profesor).pk}/', corpu, format='json'
        )

    def test_delete_removes_the_teacher(self):
        response = self.hamos(password=SENHA_ADMIN)
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(User.objects.filter(pk=self.profesor.pk).exists())

    def test_delete_cascades_to_the_whole_attendance_history(self):
        from datetime import time

        from attendance.models import ListaPrezensa, Marka, Prezensa

        from .tests_helpers import punch_evidence

        prezensa = Prezensa.objects.ba_loron(self.profesor, date(2026, 2, 18))
        marka = prezensa.checkin(oras=time(8, 3), **punch_evidence())
        foto_path = marka.foto.path
        self.assertTrue(os.path.exists(foto_path))

        response = self.hamos(password=SENHA_ADMIN)
        self.assertEqual(response.status_code, 204, response.content)

        self.assertFalse(User.objects.filter(pk=self.profesor.pk).exists())
        self.assertEqual(ListaPrezensa.objects.count(), 0)
        self.assertEqual(Prezensa.objects.count(), 0)
        self.assertEqual(Marka.objects.count(), 0)
        # The evidence file goes with the rows, not left orphaned on disk.
        self.assertFalse(os.path.exists(foto_path))

    def test_delete_without_password_is_refused(self):
        response = self.hamos()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'password_presiza')
        self.assertTrue(User.objects.filter(pk=self.profesor.pk).exists())

    def test_delete_with_wrong_password_is_refused(self):
        response = self.hamos(password='sala-tebes')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'password_sala')
        self.assertTrue(User.objects.filter(pk=self.profesor.pk).exists())

    def test_the_targets_password_does_not_work(self):
        # The check is on the caller, not on whoever is being removed.
        self.profesor.set_password('senha-profesor')
        self.profesor.save()

        response = self.hamos(password='senha-profesor')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'password_sala')
        self.assertTrue(User.objects.filter(pk=self.profesor.pk).exists())

    def test_an_admin_cannot_delete_their_own_account(self):
        # A staff account carrying role=PROFESSOR can reach its own row.
        self.admin.role = User.Role.PROFESSOR
        self.admin.save()

        response = self.hamos(profesor=self.admin, password=SENHA_ADMIN)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'rasik')
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_an_admin_account_cannot_be_deleted(self):
        seluk = User.objects.create_superuser(
            email='seluk@eti-dili.tl', password='x', numeru_id=99,
            naran_kompletu='Admin Seluk',
        )
        response = self.hamos(profesor=seluk, password=SENHA_ADMIN)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'eh_admin')
        self.assertTrue(User.objects.filter(pk=seluk.pk).exists())

    # -- Reset password -------------------------------------------------

    def reset(self, profesor=None, **corpu):
        alvo = profesor or self.profesor
        return self.client.post(
            f'/api/profesor/{alvo.pk}/reset-password/', corpu, format='json'
        )

    def test_reset_sets_the_new_password(self):
        response = self.reset(
            password_foun='SenhaFoun-2026', password_konfirma='SenhaFoun-2026'
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.profesor.refresh_from_db()
        self.assertTrue(self.profesor.check_password('SenhaFoun-2026'))
        # The plain text is never echoed back -- the admin typed it.
        self.assertNotIn('SenhaFoun-2026', response.content.decode())

    def test_reset_revokes_the_teachers_open_sessions(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(self.profesor)
        self.reset(
            password_foun='SenhaFoun-2026', password_konfirma='SenhaFoun-2026'
        )

        # The phone that was already logged in can no longer refresh.
        response = self.client.post(
            '/api/auth/refresh/', {'refresh': str(refresh)}, format='json'
        )
        self.assertEqual(response.status_code, 401)

    def test_reset_refuses_when_the_two_fields_differ(self):
        response = self.reset(
            password_foun='SenhaFoun-2026', password_konfirma='Seluk-2026'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'password_la_hanesan')
        self.profesor.refresh_from_db()
        self.assertFalse(self.profesor.check_password('SenhaFoun-2026'))

    def test_reset_without_the_fields_is_refused(self):
        response = self.reset()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'password_presiza')

    def test_reset_refuses_a_weak_password(self):
        response = self.reset(password_foun='123', password_konfirma='123')
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body['code'], 'password_fraku')
        self.assertTrue(body['erros'])

    def test_reset_refuses_an_admin_target(self):
        seluk = User.objects.create_superuser(
            email='seluk@eti-dili.tl', password='x', numeru_id=99,
            naran_kompletu='Admin Seluk',
        )
        response = self.reset(
            profesor=seluk,
            password_foun='SenhaFoun-2026', password_konfirma='SenhaFoun-2026',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'eh_admin')

    def test_reset_refuses_your_own_account(self):
        self.admin.role = User.Role.PROFESSOR
        self.admin.save()
        response = self.reset(
            profesor=self.admin,
            password_foun='SenhaFoun-2026', password_konfirma='SenhaFoun-2026',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'rasik')

    def test_an_ordinary_teacher_cannot_reset(self):
        self.client.force_authenticate(self.profesor)
        response = self.reset(
            profesor=self.inativu,
            password_foun='SenhaFoun-2026', password_konfirma='SenhaFoun-2026',
        )
        self.assertEqual(response.status_code, 403)

    def test_an_ordinary_teacher_cannot_delete(self):
        self.client.force_authenticate(self.profesor)
        self.assertEqual(self.hamos(password=SENHA_ADMIN).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.profesor.pk).exists())

    def test_anonymous_cannot_delete(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.hamos(password=SENHA_ADMIN).status_code, 401)
        self.assertTrue(User.objects.filter(pk=self.profesor.pk).exists())

    # -- Habilitasaun literária ------------------------------------------

    def test_the_roster_exposes_the_qualification_fields(self):
        self.profesor.nivel_edukasaun = User.NivelEdukasaun.LICENCIADO
        self.profesor.area_estudu = 'Gestão Informática'
        self.profesor.disiplina_hanorin = 'Sistema Base de Dados'
        self.profesor.save()

        linha = next(
            r for r in self.client.get('/api/profesor/').json()
            if r['id'] == self.profesor.pk
        )
        self.assertEqual(linha['nivel_edukasaun'], 'LICENCIADO')
        self.assertEqual(linha['nivel_edukasaun_display'], 'Licenciado')
        self.assertEqual(linha['area_estudu'], 'Gestão Informática')
        self.assertEqual(linha['disiplina_hanorin'], 'Sistema Base de Dados')

    def test_the_roster_writes_them_on_create(self):
        response = self.client.post('/api/profesor/', {
            'numeru_id': 54,
            'naran_kompletu': 'Elio Espirito Santo da Costa Ximenes',
            'email': 'elio@eti-dili.tl',
            'kargu': 'Assistencia na área Informática',
            'nivel_edukasaun': 'UNIVERSITARIA',
            'area_estudu': 'Informatica',
            'disiplina_hanorin': 'Tec. Multimedia',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)

        foun = User.objects.get(numeru_id=54)
        self.assertEqual(foun.nivel_edukasaun, 'UNIVERSITARIA')
        self.assertEqual(foun.area_estudu, 'Informatica')
        self.assertEqual(foun.disiplina_hanorin, 'Tec. Multimedia')

    def test_the_roster_updates_them(self):
        response = self.client.patch(
            f'/api/profesor/{self.profesor.pk}/',
            {'nivel_edukasaun': 'MESTRADO', 'area_estudu': 'Contabilidade'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.profesor.refresh_from_db()
        self.assertEqual(self.profesor.nivel_edukasaun, 'MESTRADO')
        self.assertEqual(self.profesor.area_estudu, 'Contabilidade')

    def test_an_unknown_nivel_is_refused(self):
        response = self.client.patch(
            f'/api/profesor/{self.profesor.pk}/',
            {'nivel_edukasaun': 'DOUTOR_INVENTADU'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('nivel_edukasaun', response.json())

    def test_every_level_on_the_school_roster_is_a_valid_choice(self):
        """
        The published "Dadus Professores" sheet uses these six; Universitária
        and Finalista were missing from the model until 2026-08-12.
        """
        for nivel in ('LICENCIADO', 'POST_GRADUACAO', 'UNIVERSITARIA',
                      'BACHARELATU', 'MESTRADO', 'FINALISTA'):
            self.assertIn(nivel, User.NivelEdukasaun.values)

    def test_ordinary_teacher_cannot_use_the_roster(self):
        self.client.force_authenticate(self.profesor)
        self.assertEqual(self.client.get('/api/profesor/').status_code, 403)
        self.assertEqual(
            self.client.post('/api/profesor/', {}, format='json').status_code, 403
        )


class TrokaPasswordTests(APITestCase):
    """`POST /api/auth/troka-password/` -- change your own password."""

    URL = '/api/auth/troka-password/'
    TUAN = 'SenhaTuan-2026'
    FOUN = 'SenhaFoun-2026'

    def setUp(self):
        self.profesor = User.objects.create_user(
            email='martinho@eti-dili.tl', numeru_id=6, password=self.TUAN,
            naran_kompletu='Martinho Martins',
        )
        self.admin = User.objects.create_superuser(
            email='joao@eti-dili.tl', numeru_id=1, password=self.TUAN,
            naran_kompletu='João Gaio',
        )
        self.client.force_authenticate(self.profesor)

    def troka(self, **corpu):
        return self.client.post(self.URL, corpu, format='json')

    def test_a_teacher_changes_their_own_password(self):
        response = self.troka(
            password_tuan=self.TUAN, password_foun=self.FOUN,
            password_konfirma=self.FOUN,
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.profesor.refresh_from_db()
        self.assertTrue(self.profesor.check_password(self.FOUN))
        self.assertFalse(self.profesor.check_password(self.TUAN))
        self.assertNotIn(self.FOUN, response.content.decode())

    def test_an_admin_can_change_their_own_password(self):
        """
        The roster refuses `rasik` and `eh_admin`, so this route is the only
        way an administrator can change a password at all.
        """
        self.client.force_authenticate(self.admin)
        response = self.troka(
            password_tuan=self.TUAN, password_foun=self.FOUN,
            password_konfirma=self.FOUN,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(self.FOUN))

    def test_it_returns_a_working_token_pair(self):
        """
        The change revokes every refresh token, including the caller's own, so
        a fresh pair comes back or the dashboard would bounce to /login in the
        middle of the action.
        """
        response = self.troka(
            password_tuan=self.TUAN, password_foun=self.FOUN,
            password_konfirma=self.FOUN,
        )
        body = response.json()
        self.assertTrue(body['access'])

        # Drop the forced auth *before* setting the header: DRF's
        # force_authenticate(None) calls logout(), which clears credentials --
        # the other order wipes the token we are trying to test.
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {body["access"]}')
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 200)

    def test_other_sessions_are_revoked(self):
        from rest_framework_simplejwt.tokens import RefreshToken

        telefone = RefreshToken.for_user(self.profesor)
        self.troka(
            password_tuan=self.TUAN, password_foun=self.FOUN,
            password_konfirma=self.FOUN,
        )
        response = self.client.post(
            '/api/auth/refresh/', {'refresh': str(telefone)}, format='json'
        )
        self.assertEqual(response.status_code, 401)

    def test_the_old_password_must_be_right(self):
        response = self.troka(
            password_tuan='sala', password_foun=self.FOUN,
            password_konfirma=self.FOUN,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'password_tuan_sala')
        self.profesor.refresh_from_db()
        self.assertTrue(self.profesor.check_password(self.TUAN))

    def test_the_two_new_fields_must_match(self):
        response = self.troka(
            password_tuan=self.TUAN, password_foun=self.FOUN,
            password_konfirma='Seluk-2026',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'password_la_hanesan')

    def test_the_new_password_must_differ_from_the_old(self):
        response = self.troka(
            password_tuan=self.TUAN, password_foun=self.TUAN,
            password_konfirma=self.TUAN,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'password_hanesan_tuan')

    def test_a_weak_new_password_is_refused(self):
        response = self.troka(
            password_tuan=self.TUAN, password_foun='123', password_konfirma='123',
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body['code'], 'password_fraku')
        self.assertTrue(body['erros'])

    def test_missing_fields_are_refused(self):
        response = self.troka()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'password_presiza')

    def test_anonymous_is_refused(self):
        self.client.force_authenticate(None)
        response = self.troka(
            password_tuan=self.TUAN, password_foun=self.FOUN,
            password_konfirma=self.FOUN,
        )
        self.assertEqual(response.status_code, 401)
