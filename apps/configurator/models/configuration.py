from django.db.models import (
    PROTECT,
    SET_NULL,
    CharField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel
from apps.core.utils import next_number


class Configuration(TimeStampedModel):
    """Bazaviy model ustidan yig'ilgan mijoz konfiguratsiyasi (chernovik).

    Ikki xil rejim (TZ 6.2):
      build  — butlovchilardan yangi mahsulot yig'iladi;
      modify — ombordagi TAYYOR mahsulot olinadi, ichi o'zgartiriladi:
               qo'shilgan qism ombordan chiqadi, yechib olingani omborga
               qaytadi (narxi bilan) va bu haqda bugalterga xabar boradi.
    """

    class Mode(TextChoices):
        BUILD = 'build', "Butlovchilardan yig'ish"
        MODIFY = 'modify', "Tayyor mahsulotni o'zgartirish"

    class Status(TextChoices):
        DRAFT = 'draft', 'Chernovik'
        READY = 'ready', 'Tayyor'
        ATTACHED = 'attached', 'Buyurtmaga biriktirilgan'
        CANCELLED = 'cancelled', 'Bekor qilingan'

    number = CharField(max_length=30, unique=True, blank=True)
    client = ForeignKey(
        'clients.Client', PROTECT, related_name='configurations',
        null=True, blank=True,
    )
    base_product = ForeignKey('inventory.Product', PROTECT, related_name='configurations')
    warehouse = ForeignKey(
        'inventory.Warehouse', PROTECT, related_name='configurations',
        null=True, blank=True,
    )
    act = ForeignKey(
        'configurator.Act', PROTECT, related_name='configurations',
        null=True, blank=True,
    )
    purchase = ForeignKey(
        'purchases.Purchase', SET_NULL, related_name='configurations',
        null=True, blank=True,
    )
    # Yakunlangach yaratiladigan (yoki topiladigan) tayyor variant — TZ 6.2
    variant = ForeignKey(
        'inventory.Product', SET_NULL, related_name='source_configurations',
        null=True, blank=True,
    )
    mode = CharField(max_length=20, choices=Mode.choices, default=Mode.BUILD)
    status = CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    note = TextField(blank=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='configurations',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.number} — {self.base_product}'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_number(Configuration, 'CFG')
        super().save(*args, **kwargs)

    @property
    def items_total(self):
        return sum((item.subtotal for item in self.items.all()), 0)

    @property
    def signature(self):
        """Tarkib imzosi — bir xil kombinatsiyani tanish uchun (TZ 6.2)."""
        from apps.inventory.services import configuration_signature

        return configuration_signature(
            self.base_product_id,
            [(item.component_id, item.quantity) for item in self.items.all()],
        )

    @property
    def matching_variant(self):
        """Xuddi shu tarkib omborda tayyor pozitsiya sifatida bormi?

        Bazaviy modelning o'zi ham tayyor pozitsiya: tarkib zavod tarkibiga
        teng bo'lsa, aynan bazaviy model va uning ombordagi narxi qo'llanadi.
        """
        from apps.inventory.models import Product

        if not self.items.exists():
            return None
        signature = self.signature
        if self.base_product and self.base_product.composition_signature == signature:
            return self.base_product
        return Product.objects.filter(signature=signature).first()

    @property
    def total_price(self):
        """Tayyor variant bo'lsa — ombordagi narxi, aks holda qatorlar yig'indisi."""
        variant = self.variant or self.matching_variant
        if variant and variant.stock_price:
            return variant.stock_price
        return self.items_total

    @property
    def changes(self):
        """Zavod tarkibiga nisbatan farq: qo'shilganlar va yechib olinganlar."""
        spec_map = {}
        for spec in self.base_product.specs.select_related('component'):
            spec_map[spec.component_id] = spec_map.get(spec.component_id, 0) + spec.quantity

        item_map, components = {}, {}
        for item in self.items.select_related('component'):
            item_map[item.component_id] = item_map.get(item.component_id, 0) + item.quantity
            components[item.component_id] = item.component
        for spec in self.base_product.specs.select_related('component'):
            components.setdefault(spec.component_id, spec.component)

        added, removed = [], []
        for component_id, component in components.items():
            diff = item_map.get(component_id, 0) - spec_map.get(component_id, 0)
            if diff > 0:
                added.append({'component': component, 'quantity': diff})
            elif diff < 0:
                removed.append({
                    'component': component,
                    'quantity': -diff,
                    'unit_price': component.stock_price,
                })
        return {'added': added, 'removed': removed}

    @property
    def missing_items(self):
        """Omborda yetishmayotgan, ya'ni kirim qilinishi kerak bo'lgan qatorlar."""
        return [item for item in self.items.all() if item.shortage > 0]

    @property
    def items_without_price(self):
        """Narxi aniqlanmagan qatorlar — yakunlashga to'sqinlik qiladi."""
        return [item for item in self.items.all() if item.needs_price]
