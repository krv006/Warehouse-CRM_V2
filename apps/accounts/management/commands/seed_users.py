from django.core.management.base import BaseCommand
from django.db.transaction import atomic

from apps.accounts.models import User

DEFAULT_PASSWORD = 'Ombor2026!'

DEMO_USERS = [
    {
        'username': 'admin',
        'first_name': 'Kamronbek',
        'last_name': 'Rustamov',
        'email': 'admin@thesofmebel.uz',
        'phone': '+998901110001',
        'role': User.Role.ADMIN,
        'is_staff': True,
        'is_superuser': True,
    },
    {
        'username': 'bugalter',
        'first_name': 'Nodira',
        'last_name': 'Yusupova',
        'email': 'bugalter@thesofmebel.uz',
        'phone': '+998901110002',
        'role': User.Role.BUGALTER,
        'is_staff': True,
    },
    {
        'username': 'buyurtmachi',
        'first_name': 'Shohrux',
        'last_name': 'Nazarov',
        'email': 'buyurtmachi@thesofmebel.uz',
        'phone': '+998901110005',
        'role': User.Role.SUPPLIER,
    },
    {
        'username': 'sales1',
        'first_name': 'Jasur',
        'last_name': 'Ergashev',
        'email': 'sales1@thesofmebel.uz',
        'phone': '+998901110003',
        'role': User.Role.SALES,
    },
    {
        'username': 'sales2',
        'first_name': 'Dilnoza',
        'last_name': 'Qodirova',
        'email': 'sales2@thesofmebel.uz',
        'phone': '+998901110004',
        'role': User.Role.SALES,
    },
]


class Command(BaseCommand):
    """Sinov uchun har bir rolga foydalanuvchi ochadi."""

    help = 'Demo foydalanuvchilar: admin, bugalter, buyurtmachi, sales1, sales2'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            default=DEFAULT_PASSWORD,
            help=f'Barchasi uchun parol (default: {DEFAULT_PASSWORD})',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Mavjud foydalanuvchilarning paroli va rolini qayta yozadi',
        )

    @atomic
    def handle(self, *args, **options):
        password = options['password']
        force = options['force']
        rows = []

        for data in DEMO_USERS:
            fields = dict(data)
            username = fields.pop('username')
            user, created = User.objects.get_or_create(username=username, defaults=fields)

            if created:
                status = "qo'shildi"
            elif force:
                for field, value in fields.items():
                    setattr(user, field, value)
                status = 'yangilandi'
            else:
                rows.append((username, user.get_role_display(), '(eskisi)', 'mavjud, tegilmadi'))
                continue

            user.set_password(password)
            user.save()
            rows.append((username, user.get_role_display(), password, status))

        self.stdout.write('')
        self.stdout.write(f'{"Login":<12}{"Rol":<16}{"Parol":<14}Holat')
        self.stdout.write('-' * 56)
        for username, role, shown, status in rows:
            self.stdout.write(f'{username:<12}{role:<16}{shown:<14}{status}')
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'DIQQAT: bu sinov foydalanuvchilari. Ishga tushgach parollarni '
            "almashtiring yoki keraksizlarini o'chiring."
        ))
        self.stdout.write(self.style.SUCCESS(
            'Kirish: POST /api/auth/login/ {"username": "...", "password": "..."}'
        ))
