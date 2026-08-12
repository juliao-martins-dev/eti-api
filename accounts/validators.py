"""
Password validators that speak Tetun.

Django's four built-in validators answer in English, and there is no Tetun
locale to translate them with -- so `validate_password` was the one place in
the API that broke into English, right where a teacher or an administrator is
being told their password was refused.

Each class here wraps its Django original: the rule itself is untouched, only
the wording it fails with. Reimplementing the checks would mean re-deriving
`CommonPasswordValidator`'s word list and `UserAttributeSimilarityValidator`'s
ratio, and inheriting them keeps that logic where Django maintains it.
"""

from django.contrib.auth.password_validation import (
    CommonPasswordValidator,
    MinimumLengthValidator,
    NumericPasswordValidator,
    UserAttributeSimilarityValidator,
)
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class TamanMinimuValidator(MinimumLengthValidator):
    """MinimumLengthValidator, refused in Tetun."""

    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError:
            raise ValidationError(
                _("Password ne'e badak liu. Tenke iha karakter %(min_length)d ka liu."),
                code='password_too_short',
                params={'min_length': self.min_length},
            )

    def get_help_text(self):
        return _(
            "Password tenke iha karakter %(min_length)d ka liu."
        ) % {'min_length': self.min_length}


class HanesanDadusValidator(UserAttributeSimilarityValidator):
    """
    UserAttributeSimilarityValidator, refused in Tetun.

    The attribute that clashed is carried over from Django's own params -- it
    is the model's `verbose_name`, and those are already written in Tetun on
    `accounts.User`.
    """

    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError as exc:
            naran = (exc.params or {}).get('verbose_name', _('dadus konta'))
            raise ValidationError(
                _("Password ne'e hanesan liu ho %(verbose_name)s. "
                  "Favor hili password ne'ebe la iha ita-nia dadus."),
                code='password_too_similar',
                params={'verbose_name': naran},
            )

    def get_help_text(self):
        return _("Password la bele hanesan ho naran, email ka numeru ID.")


class PasswordKomunValidator(CommonPasswordValidator):
    """CommonPasswordValidator, refused in Tetun."""

    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError:
            raise ValidationError(
                _("Password ne'e komun tebes no fasil atu sik. "
                  "Favor hili seluk."),
                code='password_too_common',
            )

    def get_help_text(self):
        return _("Password la bele ida ne'ebe komun liu.")


class NumeruDeitValidator(NumericPasswordValidator):
    """NumericPasswordValidator, refused in Tetun."""

    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError:
            raise ValidationError(
                _("Password ne'e numeru de'it. Tenke iha letra ka simbolu."),
                code='password_entirely_numeric',
            )

    def get_help_text(self):
        return _("Password la bele numeru de'it.")
