from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import HotWheelsModel

from .models import Collection, CollectionItem


class CollectionTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email='owner@example.com', password='ComplexPass123')
        self.other = User.objects.create_user(email='other@example.com', password='ComplexPass123')
        self.model_obj = HotWheelsModel.objects.create(
            app_id='abc123',
            toy='HCT05',
            number='001',
            model_name='1970 Pontiac Firebird',
            series='HW Dream Garage',
            series_number='1/5',
            photo_url='https://example.com/car.jpg',
        )
        self.public_collection = Collection.objects.create(
            owner=self.owner, name='Publiczna', visibility=Collection.VISIBILITY_PUBLIC
        )
        self.private_collection = Collection.objects.create(
            owner=self.owner, name='Prywatna', visibility=Collection.VISIBILITY_PRIVATE
        )

    def test_public_collection_visible(self):
        response = self.client.get(reverse('collections:collection-detail', args=[self.public_collection.pk]))
        self.assertEqual(response.status_code, 200)

    def test_private_collection_hidden_for_other_user(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('collections:collection-detail', args=[self.private_collection.pk]))
        self.assertEqual(response.status_code, 404)

    def test_owner_can_add_item(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': self.model_obj.pk,
                'quantity': 2,
                'condition': 'mint',
                'packaging_state': 'carded',
                'notes': 'Test',
                'is_favorite': True,
            },
        )
        self.assertRedirects(response, self.private_collection.get_absolute_url())
        self.assertTrue(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj).exists())
