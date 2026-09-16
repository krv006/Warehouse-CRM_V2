from django.db.models import Model, DateTimeField


class TimeStampedModel(Model):
    """Barcha modellar uchun umumiy vaqt maydonlari."""

    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']


class StatusTrackedModel(TimeStampedModel):
    """Holatli hujjat: `status` qachon o'zgarganini o'zi yozib boradi.

    TOPSHIRIQ #3 (SLA): `updated_at` yaroqsiz — izoh tahriri ham uni
    yangilaydi; `status_changed_at` esa faqat holat haqiqatan o'zgarganda
    yoziladi. Muddat nazorati ("bir ish kunidan ortiq turgan ish") aynan
    shu maydondan hisoblanadi.

    Diqqat: `queryset.update(status=...)` `save()` ni chetlab o'tadi —
    SLA qamrovidagi holatlarni servislar doim `save()` bilan o'zgartiradi.
    """

    status_changed_at = DateTimeField(null=True, blank=True)

    class Meta(TimeStampedModel.Meta):
        abstract = True

    @classmethod
    def from_db(cls, db, field_names, values, **kwargs):
        instance = super().from_db(db, field_names, values, **kwargs)
        instance._db_status = getattr(instance, 'status', None)
        return instance

    def save(self, *args, **kwargs):
        from django.utils.timezone import now

        db_status = getattr(self, '_db_status', None)
        if self.pk is None or db_status != self.status:
            self.status_changed_at = now()
            update_fields = kwargs.get('update_fields')
            if update_fields is not None and 'status_changed_at' not in update_fields:
                kwargs['update_fields'] = list(update_fields) + ['status_changed_at']
        super().save(*args, **kwargs)
        self._db_status = self.status
