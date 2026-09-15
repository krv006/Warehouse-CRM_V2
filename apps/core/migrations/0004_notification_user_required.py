from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def fix_null_users(apps, schema_editor):
    """§4.4: user=None "e'lon taxtasi" yozuvlari — adminga biriktiriladi.

    Admin topilmasa (bo'sh baza) shunchaki o'chiriladi: bu eski broadcast
    xabarlar, aniq egasi yo'q.
    """
    Notification = apps.get_model('core', 'Notification')
    User = apps.get_model('accounts', 'User')
    admin = (
        User.objects.filter(role='admin', is_active=True).order_by('id').first()
        or User.objects.filter(is_superuser=True).order_by('id').first()
    )
    orphans = Notification.objects.filter(user__isnull=True)
    if admin:
        orphans.update(user=admin)
    else:
        orphans.delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0003_companyprofile_admin_approval_threshold_and_more'),
    ]

    operations = [
        migrations.RunPython(fix_null_users, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='notification',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='notifications',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
