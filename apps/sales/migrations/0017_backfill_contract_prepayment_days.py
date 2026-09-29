# 23-§2(b)/25-§2: migratsiyadan oldingi qatorlarda `prepayment_days` bo'sh
# qoladi — `Contract.save()` faqat KEYINGI saqlashda to'ldiradi, eskilariga
# birov tegmasa umrbod `None` bo'lib qoladi va hujjatda "None" chiqadi.

from django.db import migrations


def backfill_prepayment_days(apps, schema_editor):
    Contract = apps.get_model('sales', 'Contract')
    CompanyProfile = apps.get_model('core', 'CompanyProfile')
    profile = CompanyProfile.objects.first()
    days = profile.contract_reservation_days if profile else 7
    Contract.objects.filter(prepayment_days__isnull=True).update(prepayment_days=days)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0016_contract_prepayment_days'),
        ('core', '0009_companyprofile_default_customs_fee_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_prepayment_days, noop),
    ]
