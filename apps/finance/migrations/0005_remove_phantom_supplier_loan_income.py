from django.db import migrations


def remove_phantom_income(apps, schema_editor):
    """TOPSHIRIQ-2 #1: ta'minotchi qarzi uchun yozilgan soxta KIRIMlar o'chiriladi.

    Bu yozuvlar kassada hech qachon bo'lmagan pulni ko'rsatib turardi
    (qarz — majburiyat, kirim emas). O'chirilgach kassa qoldig'i kamayadi —
    bu KUTILGAN natija: fantom pul yo'qoladi, haqiqiy raqam qoladi.
    Hisobot migratsiya logida chiqadi (nechta yozuv, jami summa).
    """
    CashTransaction = apps.get_model('finance', 'CashTransaction')
    phantoms = CashTransaction.objects.filter(
        category__code='loan',
        direction='in',
        loan__source='supplier',
    )
    count = phantoms.count()
    total = sum((row.amount for row in phantoms), 0)
    if count:
        print(
            f"\n  [finance.0005] Fantom qarz kirimlari o'chirilmoqda: "
            f"{count} ta yozuv, jami {total} — kassa qoldig'i shu summaga kamayadi.",
        )
    phantoms.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0004_expenserequest_status_changed_at'),
    ]

    operations = [
        migrations.RunPython(remove_phantom_income, migrations.RunPython.noop),
    ]
