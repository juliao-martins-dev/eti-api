import os
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from .models import User

MEDIA_TEMP = override_settings(MEDIA_ROOT=tempfile.mkdtemp())

SENHA = 'senha-forte-123'


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
        tuan = self.profesor.foto.path

        response = self.client.patch(
            '/api/auth/me/', {'foto': foto('foun.jpg')}, format='multipart'
        )
        self.assertEqual(response.status_code, 200, response.content)

        # The whole profile comes back, pointing at the new file.
        body = response.json()
        self.assertIn('foun', body['foto'])
        self.assertEqual(body['email'], self.profesor.email)
        self.assertEqual(body['numeru_id'], 6)

        self.profesor.refresh_from_db()
        self.assertIn('foun', self.profesor.foto.name)
        self.assertFalse(os.path.exists(tuan), 'the replaced file should be gone')

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


class ProfesorApiTests(APITestCase):
    """The dashboard roster: /api/profesor/ (plan R1, R3, R4)."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email='joao@eti-dili.tl', password='x', numeru_id=1,
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
        self.assertNotIn('João Gaio', naran)

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

    def test_delete_and_put_are_not_allowed(self):
        self.assertEqual(
            self.client.delete(f'/api/profesor/{self.profesor.pk}/').status_code, 405
        )
        self.assertEqual(
            self.client.put(
                f'/api/profesor/{self.profesor.pk}/', {}, format='json'
            ).status_code,
            405,
        )

    def test_ordinary_teacher_cannot_use_the_roster(self):
        self.client.force_authenticate(self.profesor)
        self.assertEqual(self.client.get('/api/profesor/').status_code, 403)
        self.assertEqual(
            self.client.post('/api/profesor/', {}, format='json').status_code, 403
        )
