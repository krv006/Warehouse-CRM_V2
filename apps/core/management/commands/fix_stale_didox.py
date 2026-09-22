from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """QOLGAN-ISHLAR #1 (SHT-00058): eski, ESKI Didox iziga tayanib xato
    `approved` bo'lgan shartnomalarni `ready_for_didox`ga qaytaradi.

    12-§1 dagi orqaga moslik sharti 12-§6 ni hisobga olmagan edi:
    `didox_accepted_at` rad etishda tozalanmaydi, shuning uchun rad etilib
    qayta boshlangan shartnoma eski (endi haqiqiy emas) Didox izidan
    to'g'ridan `approved`ga sakrab, mijozdan hujjatsiz pul so'ragan.

    Faqat hali PUL KELMAGAN (`approved`, `active` emas) yozuvlarga tegadi —
    xavfsiz, moliyaviy holatga ta'sir qilmaydi.
    """

    help = (
        "ESKI Didox iziga tayanib xato 'approved' bo'lgan shartnomalarni "
        "'ready_for_didox'ga qaytaradi; --dry-run — faqat ro'yxat."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Hech narsa yozmaydi — nima qilinishini ko'rsatadi",
        )

    def handle(self, *args, **options):
        from apps.sales.models import Contract
        from apps.sales.services import _didox_valid_for_current_cycle

        dry = options['dry_run']
        fixed = 0
        for contract in Contract.objects.filter(status=Contract.Status.APPROVED).order_by('pk'):
            if _didox_valid_for_current_cycle(contract):
                continue
            fixed += 1
            if dry:
                self.stdout.write(
                    f'{contract.number}: ready_for_didox ga qaytariladi '
                    f'(didox_accepted_at: {contract.didox_accepted_at})'
                )
                continue
            Contract.objects.filter(pk=contract.pk).update(
                status=Contract.Status.READY_FOR_DIDOX,
            )
            self.stdout.write(f'{contract.number}: ready_for_didox ga qaytarildi')

        self.stdout.write(self.style.SUCCESS(
            ('[DRY-RUN] ' if dry else '') + f'Tayyor: {fixed} ta shartnoma tuzatildi.'
        ))
