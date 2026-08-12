import uuid
from pathlib import PurePath

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

#: Extensions Pillow has already validated by the time we get here. Anything
#: else becomes .jpg rather than trusting a name that came from a client.
EXTENSAUN_FOTO = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}


def naran_foto_uniku(prefiksu, filename):
    """
    A name no upload will ever be given twice.

    Both clients send the same filename every time ("foto.jpg", "punch.jpg"),
    and Django frees a name as soon as the previous file is deleted -- so names
    were being recycled. A URL a browser had cached could then 404, or worse,
    resolve to a *different* teacher's photo. A uuid ends that for good.
    """
    sufiksu = PurePath(filename).suffix.lower()
    if sufiksu not in EXTENSAUN_FOTO:
        sufiksu = '.jpg'
    return f'{prefiksu}/{uuid.uuid4().hex}{sufiksu}'


def foto_perfil(instance, filename):
    """Profile photo -- `upload_to` for `User.foto`."""
    return naran_foto_uniku('fotos', filename)


#: ARÉA ESTUDU as it appears on the school's roster. Served to the dashboard so
#: an administrator picks from the list instead of retyping, but the field is
#: deliberately **free text**: the source sheet itself carries variants
#: ("Engenharia Civil" / "Engenaria", "Técnica Informática" / "Informatica"),
#: and a choices field would reject a teacher whose area is simply new.
AREA_ESTUDU_SUJERE = [
    'Administração Público',
    'Contabilidade',
    'Educação',
    'Eletrônica / Eletrica',
    'Engenharia Civil',
    'Engenaria',
    'Económia',
    'Gestão Informática',
    'Hospitalidade e Turismo',
    'Informatica',
    'Ingenaria Industria',
    'Multimedia',
    'Sociologia',
    'Técnica Informática',
]


class UserManager(BaseUserManager):
    """Manager for the custom user model, which logs in by email."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError(_('The email address must be set.'))
        if not extra_fields.get('numeru_id'):
            raise ValueError(_('The numeru ID must be set.'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.ADMIN)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom user for ETI Dili.

    Field names follow the "Dadus Professores" table published at
    https://eti-dili.sch.tl/dadus-professores/ (NU., NARAN KOMPLETU, KARGU,
    HABILITASAUN LITERÁRIA, DISIPLINA HANORIN, NU. KONTAKTU, FOTO,
    NIVEL EDUKASAUN, ARÉA ESTUDU).
    """

    class Role(models.TextChoices):
        ADMIN = 'ADMIN', _('Administradór')
        PROFESSOR = 'PROFESSOR', _('Professór')

    class Sexu(models.TextChoices):
        MANE = 'MANE', _('Mane')
        FETO = 'FETO', _('Feto')

    class NivelEdukasaun(models.TextChoices):
        # Ordered low to high. The labels are spelled the way the school's own
        # "Dadus Professores" sheet spells them, so an administrator reading
        # the dashboard sees the same words as the paper roster.
        ENSINU_SEKUNDARIU = 'ENSINU_SEKUNDARIU', _('Ensinu Sekundáriu')
        DIPLOMA = 'DIPLOMA', _('Diploma')
        FINALISTA = 'FINALISTA', _('Finalista')
        UNIVERSITARIA = 'UNIVERSITARIA', _('Universitária')
        BACHARELATU = 'BACHARELATU', _('Bacharelato')
        LICENCIADO = 'LICENCIADO', _('Licenciado')
        POST_GRADUACAO = 'POST_GRADUACAO', _('Post Graduacao')
        MESTRADO = 'MESTRADO', _('Mestradu')
        DOUTORAMENTU = 'DOUTORAMENTU', _('Doutoramentu')

    # Login credentials -- email replaces the default username.
    username = None
    email = models.EmailField(_('email'), unique=True)

    # NU. -- the number that identifies the teacher on every school list.
    # Assigned by the school, so it is required and never reused.
    numeru_id = models.PositiveIntegerField(
        _('numeru ID'),
        unique=True,
        validators=[MinValueValidator(1)],
        help_text=_('Numeru ne\'ebé identifika profesór/a iha lista eskola nian.'),
    )

    # NARAN KOMPLETU
    naran_kompletu = models.CharField(_('naran kompletu'), max_length=150)

    role = models.CharField(
        _('role'),
        max_length=20,
        choices=Role.choices,
        default=Role.PROFESSOR,
    )
    sexu = models.CharField(
        _('sexu'),
        max_length=4,
        choices=Sexu.choices,
        blank=True,
    )

    # KARGU -- free text: Diretor, Vice Diretor I, GAT, Chefe Dep. TLP, ...
    kargu = models.CharField(_('kargu'), max_length=120, blank=True)

    # HABILITASAUN LITERÁRIA
    habilitasaun_literaria = models.CharField(
        _('habilitasaun literária'),
        max_length=120,
        blank=True,
    )

    # DISIPLINA HANORIN -- a teacher may hold more than one subject.
    disiplina_hanorin = models.CharField(
        _('disiplina hanorin'),
        max_length=255,
        blank=True,
    )

    # NU. KONTAKTU
    nu_kontaktu = models.CharField(_('nu. kontaktu'), max_length=20, blank=True)

    # FOTO
    foto = models.ImageField(_('foto'), default="fotos/default.jpg", upload_to=foto_perfil, blank=True, null=True)

    # NIVEL EDUKASAUN
    nivel_edukasaun = models.CharField(
        _('nivel edukasaun'),
        max_length=20,
        choices=NivelEdukasaun.choices,
        blank=True,
    )

    # ARÉA ESTUDU -- free text: Gestão Informática, Engenharia Civil, ...
    area_estudu = models.CharField(_('aréa estudu'), max_length=120, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['numeru_id', 'naran_kompletu']

    objects = UserManager()

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        ordering = ['naran_kompletu']

    def __str__(self):
        return self.naran_kompletu or self.email

    def get_full_name(self):
        return self.naran_kompletu

    def get_short_name(self):
        return self.naran_kompletu.split(' ')[0] if self.naran_kompletu else self.email

    @property
    def is_professor(self):
        return self.role == self.Role.PROFESSOR
