from django.test import TestCase
from django.urls import reverse
import json

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
            owner=self.owner, name='Publiczna', kind=Collection.KIND_OWNED, visibility=Collection.VISIBILITY_PUBLIC
        )
        self.private_collection = Collection.objects.create(
            owner=self.owner, name='Prywatna', kind=Collection.KIND_OWNED, visibility=Collection.VISIBILITY_PRIVATE
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

    def test_owner_can_update_collection(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('collections:collection-update', args=[self.private_collection.pk]),
            {'name': 'Nowa nazwa', 'description': 'Opis', 'kind': Collection.KIND_WISHLIST, 'visibility': Collection.VISIBILITY_PUBLIC},
        )
        self.assertRedirects(response, self.private_collection.get_absolute_url())
        self.private_collection.refresh_from_db()
        self.assertEqual(self.private_collection.name, 'Nowa nazwa')
        self.assertEqual(self.private_collection.kind, Collection.KIND_WISHLIST)

    def test_other_user_cannot_edit_collection(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('collections:collection-update', args=[self.private_collection.pk]))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_shows_stats(self):
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj, quantity=3, is_favorite=True)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('collections:dashboard'))
        self.assertContains(response, '3')

    def test_collection_detail_shows_owner_profile_link(self):
        response = self.client.get(reverse('collections:collection-detail', args=[self.public_collection.pk]))
        self.assertContains(response, reverse('accounts:public-profile', args=[self.owner.pk]))

    def test_public_collection_list_shows_public_collections(self):
        response = self.client.get(reverse('collections:public-collections'))
        self.assertContains(response, 'Publiczna')
        self.assertNotContains(response, 'Prywatna')

    def test_owner_can_export_collection_as_csv(self):
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj, quantity=2, is_favorite=True)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('collections:collection-export', args=[self.private_collection.pk, 'csv']))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('1970 Pontiac Firebird', response.content.decode())

    def test_owner_can_export_collection_as_json(self):
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj, quantity=2, is_favorite=True)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('collections:collection-export', args=[self.private_collection.pk, 'json']))
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['collection']['name'], 'Prywatna')
        self.assertEqual(payload['items'][0]['model_name'], '1970 Pontiac Firebird')

    def test_other_user_cannot_export_collection(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('collections:collection-export', args=[self.private_collection.pk, 'csv']))
        self.assertEqual(response.status_code, 404)
