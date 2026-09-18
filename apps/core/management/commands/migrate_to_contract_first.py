from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Eski oqim yozuvlarini yangi oqimga ko'chiradi (YANGI-OQIM B11).

    Yangi qoidalar (B1/B4) bo'yicha `approved` konfiguratsiya shartnomasiz
    abadiy qulflanadi: ta'minot ham, yig'ish ham shartnoma `active`
    bo'lishini talab qiladi. Bu komanda shunday konfiguratsiyalarga draft
    shartnoma ochib beradi (mijoz aniqlansa) yoki mijozsizlar ro'yxatini
    chiqaradi — ularni sales qo'lda bog'laydi.

    `pending_bugalter` dagi shartnomalar tegilmaydi: ular eski bitta
    qadamli `approve` yo'li bilan o'taveradi (endpoint qabul qiladi).
    """

    help = (
        "Shartnomasiz `approved` konfiguratsiyalarga draft SHT ochib beradi; "
        "--dry-run — faqat ro'yxat."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Hech narsa yozmaydi — nima qilinishini ko'rsatadi",
        )

    def handle(self, *args, **options):
        from apps.configurator.models import Configuration
        from apps.configurator.services import _configuration_client
        from apps.sales.models import Contract
        from apps.sales.services import create_contract_from_configuration

        dry = options['dry_run']
        stuck = (
            Configuration.objects
            .filter(status=Configuration.Status.APPROVED)
            .order_by('pk')
        )
        created = no_client = skipped = 0
        for configuration in stuck:
            has_contract = (
                configuration.contracts
                .exclude(status__in=[
                    Contract.Status.REJECTED, Contract.Status.CANCELLED,
                ])
                .exists()
            )
            if has_contract:
                skipped += 1
                continue
            client = _configuration_client(configuration)
            owner = (
                configuration.requests.filter(created_by__isnull=False)
                .order_by('-created_at').first()
            )
            actor = owner.created_by if owner else configuration.created_by
            if client is None:
                no_client += 1
                self.stdout.write(self.style.WARNING(
                    f'{configuration.number}: MIJOZ YO\'Q — shartnoma ochilmadi, '
                    "sales zayavkaga mijoz bog'lab approve'ni qaytarsin."
                ))
                continue
            if dry:
                self.stdout.write(
                    f'{configuration.number}: draft SHT ochiladi '
                    f'(mijoz: {client}, egasi: {actor})'
                )
                created += 1
                continue
            contract = create_contract_from_configuration(
                configuration, actor, client,
            )
            created += 1
            self.stdout.write(
                f'{configuration.number}: {contract.number} ochildi '
                f'(mijoz: {client})'
            )

        self.stdout.write(self.style.SUCCESS(
            ('[DRY-RUN] ' if dry else '')
            + f'Tayyor: {created} ta shartnoma ochildi, {no_client} ta mijozsiz '
            f'(qo\'lda), {skipped} ta allaqachon shartnomali.'
        ))
