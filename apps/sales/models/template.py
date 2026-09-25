from django.db.models import (
    SET_NULL,
    BooleanField,
    CharField,
    ForeignKey,
    TextField,
)

from apps.core.models import TimeStampedModel


class ContractTemplate(TimeStampedModel):
    """Sotuv bo'limining shartnoma shabloni — 1-9 bo'lim matni (21-§3.1).

    `body` — sales yozgan HTML, ichida `{{ key }}` o'rin egallovchilar
    (21-§3.3a). Rekvizit, imzo va spetsifikatsiya bloklarini shablon
    o'zi yozmaydi — ular tizim tomonidan avtomatik quriladi (21-§3.3b),
    `has_specification`/`has_requisites` faqat shu bloklar chizilsinmi
    yo'qmi belgilaydi.
    """

    name = CharField(max_length=200)
    language = CharField(max_length=5, default='ru')
    body = TextField()
    note = TextField(blank=True)
    is_active = BooleanField(default=True)
    is_default = BooleanField(default=False)
    has_specification = BooleanField(default=True)
    has_requisites = BooleanField(default=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='contract_templates',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['-is_default', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            ContractTemplate.objects.exclude(pk=self.pk).update(is_default=False)
