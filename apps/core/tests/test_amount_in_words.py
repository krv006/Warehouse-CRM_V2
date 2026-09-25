from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.utils import amount_in_words


class AmountInWordsRuTests(SimpleTestCase):
    """21-§3.4: summa so'z bilan — chegara holatlar (0, 1, 11-19, 21, million/milliard, tiyin)."""

    def test_zero(self):
        self.assertEqual(amount_in_words(0), 'Ноль сум и 00 тийин')

    def test_one(self):
        self.assertEqual(amount_in_words(1), 'Один сум и 00 тийин')

    def test_teen(self):
        self.assertEqual(amount_in_words(11), 'Одиннадцать сум и 00 тийин')
        self.assertEqual(amount_in_words(19), 'Девятнадцать сум и 00 тийин')

    def test_twenty_one(self):
        self.assertEqual(amount_in_words(21), 'Двадцать один сум и 00 тийин')

    def test_thousand_feminine(self):
        # "тысяча" ayollik — "один" emas "одна", "два" emas "две"
        self.assertEqual(amount_in_words(1000), 'Одна тысяча сум и 00 тийин')
        self.assertEqual(amount_in_words(2000), 'Две тысячи сум и 00 тийин')

    def test_million_and_fraction(self):
        self.assertEqual(
            amount_in_words(Decimal('77000000.10')),
            'Семьдесят семь миллионов сум и 10 тийин',
        )

    def test_billion(self):
        self.assertEqual(amount_in_words(1_000_000_000), 'Один миллиард сум и 00 тийин')

    def test_plural_forms(self):
        self.assertEqual(amount_in_words(5), 'Пять сум и 00 тийин')
        self.assertEqual(amount_in_words(2), 'Два сум и 00 тийин')

    def test_mixed_groups(self):
        self.assertEqual(
            amount_in_words(1234567),
            'Один миллион двести тридцать четыре тысячи пятьсот шестьдесят семь сум и 00 тийин',
        )


class AmountInWordsUzTests(SimpleTestCase):
    def test_zero(self):
        self.assertEqual(amount_in_words(0, language='uz'), "Nol so'm va 00 tiyin")

    def test_hundred_drops_bir(self):
        self.assertEqual(amount_in_words(100, language='uz'), "Yuz so'm va 00 tiyin")
        self.assertEqual(amount_in_words(200, language='uz'), "Ikki yuz so'm va 00 tiyin")

    def test_teen(self):
        self.assertEqual(amount_in_words(11, language='uz'), "O'n bir so'm va 00 tiyin")

    def test_million_and_fraction(self):
        self.assertEqual(
            amount_in_words(Decimal('77000000.10'), language='uz'),
            "Yetmish yetti million so'm va 10 tiyin",
        )
