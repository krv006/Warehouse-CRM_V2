import re
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import get_resolver

DOCS = Path(__file__).resolve().parents[3] / 'docs'
API_DOC = DOCS / '05-API.md'
ROLES_DOC = DOCS / '03-ROLES-PERMISSIONS.md'


def collect_patterns(patterns, prefix=''):
    found = []
    for pattern in patterns:
        full = prefix + str(pattern.pattern)
        if hasattr(pattern, 'url_patterns'):
            found += collect_patterns(pattern.url_patterns, full)
        else:
            found.append(full)
    return found


class DocsConsistencyTests(SimpleTestCase):
    """Hujjatlar kod bilan mos turishini tekshiradi.

    Yangi endpoint qo'shilib, hujjatga yozilmasa — shu test yiqiladi.
    """

    def setUp(self):
        self.urls = [
            url for url in collect_patterns(get_resolver().url_patterns)
            if url.startswith('api/') and url.rstrip('/') not in ('api/docs', 'api/schema')
        ]

    def test_every_endpoint_is_documented(self):
        api_text = API_DOC.read_text(encoding='utf-8')
        for url in self.urls:
            parts = url.replace('api/', '', 1).rstrip('/').split('/')
            token = parts[-1] if len(parts) > 1 and not parts[-1].startswith('<') else f'/{parts[0]}/'
            with self.subTest(url=url):
                self.assertIn(token, api_text, f'{url} — 05-API.md da yozilmagan')

    def test_permission_classes_are_documented(self):
        from apps.accounts import permissions

        roles_text = ROLES_DOC.read_text(encoding='utf-8')
        classes = [
            name for name in dir(permissions)
            if name.endswith('Access') or name.startswith('Is') or name.startswith('Can')
        ]
        for name in classes:
            if name in {'RoleAccess', 'IsAuthenticated'}:
                continue
            with self.subTest(permission=name):
                self.assertIn(name, roles_text, f'{name} — 03-ROLES-PERMISSIONS.md da yo\'q')

    def test_no_removed_names_left_in_docs(self):
        """TZ dan tashqari o'chirilgan narsalar hujjatlarda qolmasin."""
        removed = ['inventory.Category', 'CategoryViewSet', 'CategorySerializer']
        for md in DOCS.glob('*.md'):
            text = md.read_text(encoding='utf-8')
            for name in removed:
                with self.subTest(file=md.name, name=name):
                    self.assertNotIn(name, text)

    def test_endpoint_count_matches_readme(self):
        readme = (DOCS.parent / 'README.md').read_text(encoding='utf-8')
        match = re.search(r'(\d+) endpoint', readme)
        if match:
            self.assertEqual(
                int(match.group(1)), len(self.urls),
                'README dagi endpoint soni haqiqiy songa mos emas',
            )
