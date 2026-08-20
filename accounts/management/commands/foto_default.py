"""Recreate the shared profile placeholder if it has gone missing."""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.models import FOTO_DEFAULT


class Command(BaseCommand):
    help = (
        'Write the shared profile placeholder to MEDIA_ROOT if it is missing. '
        'Every account without a photo of its own points at this one file.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Overwrite the file even when one is already there.',
        )

    def handle(self, *args, **options):
        caminhu = Path(settings.MEDIA_ROOT) / Path(*FOTO_DEFAULT.split('/'))

        if caminhu.exists() and not options['force']:
            self.stdout.write(self.style.SUCCESS(
                f'Iha ona / already there: {caminhu} '
                f'({caminhu.stat().st_size} bytes). Use --force to replace it.'
            ))
            return

        try:
            from PIL import Image, ImageDraw
        except ImportError:  # pragma: no cover - Pillow is a hard dependency
            raise SystemExit('Pillow is required to generate the placeholder.')

        caminhu.parent.mkdir(parents=True, exist_ok=True)

        # A plain neutral avatar: a head and shoulders on a grey field. Drawn
        # rather than shipped so this command has nothing to depend on.
        lado = 512
        imajen = Image.new('RGB', (lado, lado), (226, 232, 240))
        desenu = ImageDraw.Draw(imajen)
        desenu.ellipse((176, 96, 336, 256), fill=(148, 163, 184))
        desenu.ellipse((96, 288, 416, 608), fill=(148, 163, 184))
        imajen.save(caminhu, format='JPEG', quality=90)

        self.stdout.write(self.style.SUCCESS(
            f'Kria ona / written: {caminhu} ({caminhu.stat().st_size} bytes)'
        ))
