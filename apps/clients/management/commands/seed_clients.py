from django.core.management.base import BaseCommand
from django.db.transaction import atomic

from apps.accounts.models import User
from apps.clients.models import Client

DEMO_CLIENTS = [
    {
        'type': Client.Type.INDIVIDUAL,
        'full_name': 'Sardor Abdullayev',
        'passport': 'AA1234567',
        'jshshir': '31201955610012',
        'phone': '+998901230001',
        'email': 'sardor@mail.uz',
        'address': 'Toshkent, Yunusobod 4-kvartal',
        'note': 'Doimiy mijoz',
    },
    {
        'type': Client.Type.INDIVIDUAL,
        'full_name': 'Gulnora Sattorova',
        'passport': 'AB7654321',
        'jshshir': '52803199020034',
        'phone': '+998901230002',
        'email': '',
        'address': 'Samarqand, Registon ko\'chasi 12',
        'note': '',
    },
    {
        'type': Client.Type.LEGAL,
        'company_name': 'Soft Mebel MCHJ',
        'inn': '305123456',
        'jshshir': '30512345600001',
        'director_name': 'Aziz Karimov',
        'phone': '+998901230003',
        'email': 'info@softmebel.uz',
        'address': 'Toshkent, Chilonzor 5-kvartal, 24-uy',
        'note': 'Yirik buyurtmachi',
    },
    {
        'type': Client.Type.LEGAL,
        'company_name': 'Navoiy Qurilish Servis',
        'inn': '306987654',
        'jshshir': '30698765400002',
        'director_name': 'Bekzod Toshmatov',
        'phone': '+998901230004',
        'email': 'office@nqs.uz',
        'address': 'Navoiy, Sanoat ko\'chasi 7',
        'note': '',
    },
]


class Command(BaseCommand):
    """Sinov uchun buyurtmachilar (2 jismoniy, 2 yuridik shaxs)."""

    help = 'Demo buyurtmachilar: 2 jismoniy va 2 yuridik shaxs'

    @atomic
    def handle(self, *args, **options):
        author = User.objects.filter(role=User.Role.SALES).first()
        rows = []

        for data in DEMO_CLIENTS:
            fields = dict(data)
            fields['created_by'] = author
            lookup = (
                {'passport': fields['passport']}
                if fields['type'] == Client.Type.INDIVIDUAL
                else {'inn': fields['inn']}
            )
            client, created = Client.objects.get_or_create(**lookup, defaults=fields)
            rows.append((
                client.display_name,
                client.get_type_display(),
                client.phone,
                "qo'shildi" if created else 'mavjud',
            ))

        self.stdout.write('')
        self.stdout.write(f'{"Nomi":<28}{"Turi":<18}{"Telefon":<16}Holat')
        self.stdout.write('-' * 74)
        for name, type_display, phone, status in rows:
            self.stdout.write(f'{name:<28}{type_display:<18}{phone:<16}{status}')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Buyurtmachilar tayyor: GET /api/clients/'))
