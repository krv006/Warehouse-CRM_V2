from django.core.management.base import BaseCommand

from apps.finance.services import ensure_default_categories


class Command(BaseCommand):
    """Kassa kategoriyalarini (kirim/chiqim yacheykalari) yaratadi."""

    help = 'Kassa uchun tizim kategoriyalarini yaratadi'

    def handle(self, *args, **options):
        created = ensure_default_categories()
        self.stdout.write(self.style.SUCCESS(f'{len(created)} ta kategoriya qo\'shildi'))
