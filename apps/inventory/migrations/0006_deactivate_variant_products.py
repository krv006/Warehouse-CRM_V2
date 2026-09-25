from django.db import migrations


def deactivate_variants(apps, schema_editor):
    """21-to'plam §1.5: mavjud yig'ilgan variantlar katalogdan yashiriladi.

    O'chirib bo'lmaydi — har biri kamida bitta `ContractItem.product`da
    turibdi, FK `PROTECT`. `is_active=False` ularni katalog, yetishmayotganlar
    va narx kutayotganlar ro'yxatidan chiqaradi (§1.4).
    """
    Product = apps.get_model('inventory', 'Product')
    Product.objects.filter(base_model__isnull=False).update(is_active=False)


def reactivate_variants(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    Product.objects.filter(base_model__isnull=False).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0005_stockreservation'),
    ]

    operations = [
        migrations.RunPython(deactivate_variants, reactivate_variants),
    ]
