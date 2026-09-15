from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def fill_owner_sales(apps, schema_editor):
    """Mavjud hisoblarga zayavka egasini zanjirdan bir marta yozib qo'yadi."""
    Replenishment = apps.get_model('procurement', 'Replenishment')
    for replenishment in Replenishment.objects.filter(
        configuration__isnull=False, owner_sales__isnull=True,
    ).select_related('configuration'):
        request = (
            replenishment.configuration.requests
            .filter(created_by__isnull=False)
            .order_by('-created_at')
            .first()
        )
        if request:
            replenishment.owner_sales_id = request.created_by_id
            replenishment.save(update_fields=['owner_sales'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('procurement', '0005_replenishment_debt_amount_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='replenishment',
            name='owner_sales',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='owned_replenishments',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(fill_owner_sales, migrations.RunPython.noop),
    ]
