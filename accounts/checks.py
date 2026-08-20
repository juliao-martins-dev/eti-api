"""
System checks for the accounts app.

Run by `manage.py check`, by `runserver` on startup, and by CI.
"""
from pathlib import Path

from django.conf import settings
from django.core.checks import Warning, register

from .models import FOTO_DEFAULT


@register()
def foto_default_iha_ona(app_configs, **kwargs):
    """
    Warn when the shared placeholder photo is missing from MEDIA_ROOT.

    Every account created without a photo points at this one file, so losing it
    breaks all of them at once -- and it lives under `media/`, which is not in
    version control. That makes it exactly the kind of thing that disappears in
    a fresh clone, a wiped media directory, or a restore that skipped the
    uploads, and is then noticed only when a teacher opens the app.

    A warning, not an error: the API still runs, and the clients fall back to
    their own bundled placeholder rather than crashing.
    """
    caminhu = Path(settings.MEDIA_ROOT) / Path(*FOTO_DEFAULT.split('/'))
    if caminhu.exists():
        return []

    return [
        Warning(
            f'The shared profile placeholder is missing: {caminhu}',
            hint=(
                f'Every account with no photo of its own points at '
                f'{FOTO_DEFAULT!r}. Put an image back at that path, or run '
                f'`manage.py foto_default` to write one.'
            ),
            id='accounts.W001',
        )
    ]
