from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.transaction import atomic


class Command(BaseCommand):
    """Demo qoldiq: har bir faol mahsulotni sog'lom darajaga to'ldiradi.

    Bazaviy model, butlovchilar va configurator yaratgan variantlar — hammasi
    yagona omborda kamida `--target` dona bo'ladi. Idempotent: yetarli qoldiq
    bo'lgan mahsulotga qayta kirim yozilmaydi, xohlagancha qayta yursa bo'ladi.
    """

    help = "Kam qolgan mahsulotlarga demo kirim yozadi (sinov uchun, idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--target', type=int, default=10,
            help='Har bir mahsulot uchun minimal qoldiq (default: 10)',
        )

    @atomic
    def handle(self, *args, **options):
        from apps.inventory.models import Product, StockMovement
        from apps.inventory.services import (
            apply_movement,
            available_quantity,
            main_warehouse,
        )

        warehouse = main_warehouse()
        target = options['target']
        topped_up = 0
        for product in Product.objects.filter(is_active=True).order_by('sku'):
            current = Decimal(available_quantity(product, warehouse))
            goal = Decimal(max(target, product.reorder_level * 2))
            if current >= goal:
                self.stdout.write(f'{product.sku:16} {current:>7} (yetarli)')
                continue
            apply_movement(
                product=product, warehouse=warehouse,
                type=StockMovement.Type.IN, quantity=goal - current,
                reason=StockMovement.Reason.PURCHASE, reference='DEMO-STOCK',
            )
            topped_up += 1
            self.stdout.write(f'{product.sku:16} {current:>7} -> {goal}')

        self.stdout.write(self.style.SUCCESS(
            f"'{warehouse.name}' to'ldirildi: {topped_up} ta mahsulotga demo kirim yozildi."
        ))
