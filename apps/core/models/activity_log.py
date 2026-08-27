from django.db.models import (
    SET_NULL,
    CharField,
    ForeignKey,
    Model,
    DateTimeField,
    TextChoices,
    TextField,
)


class ActivityLog(Model):
    """Kim, qachon, nima qilgani — admin uchun to'liq hisobot."""

    class Action(TextChoices):
        CREATE = 'create', "Qo'shildi"
        UPDATE = 'update', "O'zgartirildi"
        DELETE = 'delete', "O'chirildi"
        APPROVE = 'approve', 'Tasdiqlandi'
        REJECT = 'reject', 'Rad etildi'

    user = ForeignKey(
        'accounts.User', SET_NULL, related_name='activity_logs',
        null=True, blank=True,
    )
    action = CharField(max_length=20, choices=Action.choices)
    entity = CharField(max_length=100)
    object_id = CharField(max_length=50, blank=True)
    description = TextField(blank=True)
    created_at = DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} — {self.get_action_display()} {self.entity}'
