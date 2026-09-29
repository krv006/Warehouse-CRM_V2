from django.test import TestCase

from apps.inventory.models import Product
from apps.inventory.services import create_product_from_order


class CreateProductFromOrderDescriptionMergeTests(TestCase):
    """25-§5: takror nomda mahsulot qayta ishlatiladi, lekin yangi tavsif
    jim yo'qolmasligi kerak — eskisi ustiga qo'shiladi."""

    def test_existing_name_with_new_description_appends(self):
        Product.objects.create(sku='HP-880', name='HP 880', description='Zavod tarkibi')
        product = create_product_from_order(name='HP 880', description='Mijoz aytdi: 32GB RAM')

        self.assertEqual(Product.objects.filter(name__iexact='HP 880').count(), 1)
        self.assertIn('Zavod tarkibi', product.description)
        self.assertIn('Mijoz aytdi: 32GB RAM', product.description)

    def test_existing_name_with_blank_description_unchanged(self):
        Product.objects.create(sku='HP-880', name='HP 880', description='Zavod tarkibi')
        product = create_product_from_order(name='HP 880', description='')

        self.assertEqual(product.description, 'Zavod tarkibi')

    def test_same_description_not_duplicated(self):
        Product.objects.create(sku='HP-880', name='HP 880', description='Mijoz aytdi: 32GB RAM')
        product = create_product_from_order(name='HP 880', description='Mijoz aytdi: 32GB RAM')

        self.assertEqual(product.description.count('Mijoz aytdi: 32GB RAM'), 1)

    def test_new_name_creates_product_with_own_description(self):
        product = create_product_from_order(name='Yangi model', description='Tavsif matni')

        self.assertTrue(Product.objects.filter(name='Yangi model').exists())
        self.assertEqual(product.description, 'Tavsif matni')
