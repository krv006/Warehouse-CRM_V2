from django.db.models import (
    CASCADE,
    PROTECT,
    SET_NULL,
    CharField,
    ForeignKey,
    PositiveIntegerField,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class ConfigurationRequestLine(TimeStampedModel):
    """12-§2 (B): zayavkadagi QO'SHIMCHA talab — mijoz bir suhbatda bir
    nechta narsa so'raganda (masalan 10 ta HP 880 + 20 ta zapas SSD).

    Birinchi model so'rov o'zining `ConfigurationRequest.base_product`/
    `quantity` maydonlarida qoladi (orqaga mos — mavjud kod, roadmap,
    testlar o'zgarmaydi); bu model 2-, 3- ... talablar uchun.

    Ikki xil qator bor (topshiriqdagi tuzatish): **model** — yig'iladigan,
    konfigurator orqali o'tadi; **tovar** — tayyor mahsulot yoki butlovchi,
    yig'ish/ACT kerak emas, to'g'ridan-to'g'ri shartnoma qatoriga aylanadi.
    """

    class Kind(TextChoices):
        MODEL = 'model', "Model (yig'iladigan)"
        ITEM = 'item', 'Tovar (tayyor, konfiguratorsiz)'

    request = ForeignKey(
        'configurator.ConfigurationRequest', CASCADE, related_name='lines',
    )
    kind = CharField(max_length=10, choices=Kind.choices, default=Kind.MODEL)
    base_product = ForeignKey('inventory.Product', PROTECT, related_name='+')
    quantity = PositiveIntegerField(default=1)
    text = TextField(blank=True, help_text='Shu qatorga tegishli izoh')
    # MODEL turi: engineer ishga olganda to'ladi
    configuration = ForeignKey(
        'configurator.Configuration', SET_NULL, null=True, blank=True,
        related_name='extra_request_lines',
    )
    # ITEM turi: shartnoma ochilgach (yoki mavjudiga) qator sifatida qo'shiladi
    contract_item = ForeignKey(
        'sales.ContractItem', SET_NULL, null=True, blank=True, related_name='+',
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.request} — {self.base_product} x{self.quantity}'

    @property
    def is_complete(self):
        """Bu qator o'z yo'lini bosib o'tdimi — zayavka DONE bo'lishi uchun.

        14-§5(a): bekor qilingan model ham "tugagan" — aks holda savdodan
        chiqarilgan (`detach target=cancel`) model zayavkani abadiy ochiq
        qoldirardi (`is_fully_done` hech qachon rost bo'lmasdi).
        """
        if self.kind == self.Kind.ITEM:
            return bool(self.contract_item_id)
        return bool(
            self.configuration_id
            and self.configuration.status in ('approved', 'ready', 'sold', 'cancelled'),
        )
