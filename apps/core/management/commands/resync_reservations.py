from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Konfiguratsiya bronlarini yagona ta'rifdan qayta quradi (4-to'plam §1).

    3-to'plam §1 dan OLDIN yozilgan bronlar eski qoida bilan turadi:
    modify'da mashina ichidagi qismlar band, modelning o'zi esa ochiq.
    Oddiy yo'l bilan tuzalmaydi — saqlash faqat chernovikda, TLD kirimi
    hisobi bor hujjatnigina tuzatadi. Bu komanda har bir konfiguratsiya
    uchun `sync_configuration_reservations` ni yurgizadi: ochiq holatlar
    `required_from_stock` bo'yicha qayta band qilinadi, terminal holatlar
    (`ready`/`sold`/`cancelled`) esa bo'shatiladi. Kelajakda bron ta'rifi
    yana o'zgarsa ham shu komanda bir marta yurgiziladi.
    """

    help = (
        "Konfiguratsiya bronlarini required_from_stock bo'yicha qayta quradi; "
        "terminal holatdagilarniki bo'shatiladi."
    )

    def handle(self, *args, **options):
        from apps.configurator.models import Configuration
        from apps.inventory.models import StockReservation
        from apps.inventory.services import sync_configuration_reservations

        held = {
            Configuration.Status.DRAFT,
            Configuration.Status.PENDING_CLARIFICATION,
            Configuration.Status.PENDING_SALES,
            Configuration.Status.APPROVED,
        }

        def active_count(configuration):
            return StockReservation.objects.filter(
                configuration=configuration,
                status=StockReservation.Status.ACTIVE,
            ).count()

        resynced = released = 0
        for configuration in Configuration.objects.order_by('pk'):
            before = active_count(configuration)
            sync_configuration_reservations(configuration)
            after = active_count(configuration)
            if configuration.status in held:
                resynced += 1
                if before or after:
                    self.stdout.write(
                        f'{configuration.number} ({configuration.status}): '
                        f'{before} -> {after} bron'
                    )
            elif before:
                released += 1
                self.stdout.write(
                    f"{configuration.number} ({configuration.status}): "
                    f"{before} bron bo'shatildi (terminal holat)"
                )

        self.stdout.write(self.style.SUCCESS(
            f'Tayyor: {resynced} ta ochiq konfiguratsiya qayta qurildi, '
            f'{released} ta terminal hujjat broni bo\'shatildi.'
        ))
