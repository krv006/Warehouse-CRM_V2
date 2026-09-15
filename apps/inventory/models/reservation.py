from django.db.models import (
    CASCADE,
    PROTECT,
    SET_NULL,
    CharField,
    CheckConstraint,
    DateField,
    DecimalField,
    ForeignKey,
    Q,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class StockReservation(TimeStampedModel):
    """Ombor broni (§11.4) — qoldiqni O'ZGARTIRMAYDI, "kimga va'da qilingan"ni yozadi.

    Ikki daraja:
      soft (Rejada) — konfiguratsiya qo'yadi: ogohlantiradi, hech kimni to'smaydi;
      hard (Band)   — shartnoma qo'yadi: bu mol sotilgan hisoblanadi, boshqa
                      hujjat uni ololmaydi.

    Chiqim vaqti o'zgarmagan — u baribir to'lovda bo'ladi; bron shartnoma
    tuzilganidan to'lovgacha bo'lgan oynani yopadi. `StockMovement` ga
    qo'shilmagan, chunki harakat doim qoldiqni o'zgartiradi, bron esa yo'q.
    """

    class Kind(TextChoices):
        SOFT = 'soft', 'Rejada'
        HARD = 'hard', 'Band'

    class Status(TextChoices):
        ACTIVE = 'active', 'Faol'
        RELEASED = 'released', "Bo'shatilgan"
        SHIPPED = 'shipped', 'Chiqim qilindi'
        EXPIRED = 'expired', 'Muddati tugadi'

    product = ForeignKey('inventory.Product', PROTECT, related_name='reservations')
    warehouse = ForeignKey('inventory.Warehouse', PROTECT, related_name='reservations')
    quantity = DecimalField(max_digits=18, decimal_places=2)
    kind = CharField(max_length=10, choices=Kind.choices)
    status = CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    contract = ForeignKey(
        'sales.Contract', CASCADE, related_name='reservations',
        null=True, blank=True,
    )
    configuration = ForeignKey(
        'configurator.Configuration', CASCADE, related_name='reservations',
        null=True, blank=True,
    )

    expires_at = DateField(null=True, blank=True)
    released_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='released_reservations',
        null=True, blank=True,
    )
    release_note = TextField(blank=True)

    class Meta:
        constraints = [
            # Bron aynan bitta hujjatga tegishli: yo shartnoma, yo konfiguratsiya
            CheckConstraint(
                condition=(
                    Q(contract__isnull=False, configuration__isnull=True)
                    | Q(contract__isnull=True, configuration__isnull=False)
                ),
                name='reservation_exactly_one_owner',
            ),
        ]

    def __str__(self):
        owner = self.contract or self.configuration
        return f'{self.get_kind_display()}: {self.product} x{self.quantity} — {owner}'

    @property
    def owner_number(self):
        owner = self.contract or self.configuration
        return owner.number if owner else ''
