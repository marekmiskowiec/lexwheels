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
            year=2022,
            category='Mainline',
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
                'enabled_short_card': 'on',
                'quantity_short_card': 2,
                'condition_short_card': 'mint',
            },
        )
        self.assertRedirects(response, self.private_collection.get_absolute_url())
        self.assertTrue(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj).exists())

    def test_item_create_requires_search_before_showing_model_list(self):
        second_model = HotWheelsModel.objects.create(
            app_id='def456',
            toy='HCT06',
            number='002',
            model_name='Custom Mustang',
            year=2022,
            category='Mainline',
            series='HW Dream Garage',
            series_number='2/5',
            photo_url='https://example.com/mustang.jpg',
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse('collections:item-create', args=[self.private_collection.pk]))

        self.assertContains(response, 'Znajdź model')
        self.assertContains(response, 'Wpisz fragment nazwy')
        self.assertNotContains(response, '1970 Pontiac Firebird |')
        self.assertNotContains(response, 'Custom Mustang |')
        self.assertEqual(list(response.context['form'].fields['model'].queryset), [])

    def test_item_create_can_filter_model_list_by_search_query(self):
        second_model = HotWheelsModel.objects.create(
            app_id='def456',
            toy='HCT06',
            number='002',
            model_name='Custom Mustang',
            year=2022,
            category='Mainline',
            series='HW Dream Garage',
            series_number='2/5',
            photo_url='https://example.com/mustang.jpg',
        )
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {'q': 'Mustang'},
        )

        self.assertContains(response, 'Znalezione modele: 1')
        self.assertContains(response, 'Custom Mustang |')
        self.assertNotContains(response, '1970 Pontiac Firebird |')
        self.assertEqual(list(response.context['form'].fields['model'].queryset), [second_model])

    def test_owner_can_add_selected_model_from_broad_search_results(self):
        broad_match_models = []
        for index in range(120):
            broad_match_models.append(
                HotWheelsModel.objects.create(
                    app_id=f'broad-{index}',
                    toy=f'SUP{index:03d}',
                    number=f'{index + 2:03d}',
                    model_name=f'Toyota Supra Variant {index:03d}',
                    year=2022,
                    category='Mainline',
                    series='HW Speed Graphics',
                    series_number='1/5',
                    photo_url='https://example.com/supra.jpg',
                )
            )
        selected_model = broad_match_models[-1]
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': selected_model.pk,
                '_model_query': 'Toyota Supra',
                'enabled_short_card': 'on',
                'quantity_short_card': 1,
                'condition_short_card': 'mint',
            },
        )

        self.assertRedirects(response, self.private_collection.get_absolute_url())
        self.assertTrue(CollectionItem.objects.filter(collection=self.private_collection, model=selected_model).exists())

    def test_owner_can_add_same_model_with_different_packaging_variant(self):
        CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': self.model_obj.pk,
                'enabled_loose': 'on',
                'quantity_loose': 2,
                'condition_loose': 'good',
            },
        )

        self.assertRedirects(response, self.private_collection.get_absolute_url())
        self.assertEqual(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj).count(), 2)

    def test_owner_can_add_same_model_with_same_packaging_when_attributes_differ(self):
        CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
            is_sealed=True,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': self.model_obj.pk,
                'enabled_short_card': 'on',
                'quantity_short_card': 1,
                'condition_short_card': 'mint',
                'is_signed_short_card': 'on',
            },
        )

        self.assertRedirects(response, self.private_collection.get_absolute_url())
        self.assertEqual(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj).count(), 2)

    def test_owner_cannot_add_duplicate_model_variant(self):
        CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
            is_sealed=True,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': self.model_obj.pk,
                'enabled_short_card': 'on',
                'quantity_short_card': 2,
                'condition_short_card': 'mint',
                'is_sealed_short_card': 'on',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'już istnieje w tej kolekcji')

    def test_owner_can_add_multiple_variants_in_single_form(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': self.model_obj.pk,
                'enabled_short_card': 'on',
                'quantity_short_card': 1,
                'condition_short_card': 'mint',
                'enabled_long_card': 'on',
                'quantity_long_card': 1,
                'condition_long_card': 'good',
                'enabled_loose': 'on',
                'quantity_loose': 2,
                'condition_loose': 'good',
            },
        )

        self.assertRedirects(response, self.private_collection.get_absolute_url())
        self.assertEqual(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj).count(), 3)
        self.assertTrue(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj, packaging_state='long_card').exists())

    def test_semi_premium_item_form_hides_short_card_option(self):
        semi_premium_model = HotWheelsModel.objects.create(
            app_id='semi123',
            toy='JBY30',
            number='2/5',
            model_name='Toyota Supra',
            brand='Hot Wheels',
            year=2025,
            category='Semi Premium',
            series="Fast & Furious: Brian O'Conner Series",
            series_number='2/5',
            photo_url='https://example.com/supra.jpg',
            long_card_photo_url='https://example.com/supra-carded.jpg',
            loose_photo_url='https://example.com/supra-loose.jpg',
        )
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {'model': semi_premium_model.pk},
        )

        self.assertNotContains(response, 'Krótka karta')
        self.assertContains(response, 'Długa')
        self.assertContains(response, 'Luzak')

    def test_owner_cannot_add_semi_premium_as_short_card(self):
        semi_premium_model = HotWheelsModel.objects.create(
            app_id='semi124',
            toy='JBY30',
            number='2/5',
            model_name='Toyota Supra',
            brand='Hot Wheels',
            year=2025,
            category='Semi Premium',
            series="Fast & Furious: Brian O'Conner Series",
            series_number='2/5',
            photo_url='https://example.com/supra.jpg',
            long_card_photo_url='https://example.com/supra-carded.jpg',
            loose_photo_url='https://example.com/supra-loose.jpg',
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': semi_premium_model.pk,
                'enabled_short_card': 'on',
                'quantity_short_card': 1,
                'condition_short_card': 'mint',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Zaznacz przynajmniej jeden wariant modelu do dodania.')
        self.assertNotContains(response, 'Krótka karta')
        self.assertFalse(CollectionItem.objects.filter(collection=self.private_collection, model=semi_premium_model).exists())

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
        self.assertContains(response, 'Statystyki i wykresy')
        self.assertContains(response, 'Marki')
        self.assertContains(response, 'Hot Wheels')

    def test_collection_detail_shows_owner_profile_link(self):
        response = self.client.get(reverse('collections:collection-detail', args=[self.public_collection.pk]))
        self.assertContains(response, reverse('accounts:public-profile', args=[self.owner.pk]))

    def test_public_collection_list_shows_public_collections(self):
        response = self.client.get(reverse('collections:public-collections'))
        self.assertContains(response, 'Publiczna')
        self.assertNotContains(response, 'Prywatna')

    def test_collection_detail_can_filter_items_by_search_query(self):
        second_model = HotWheelsModel.objects.create(
            app_id='def456',
            toy='HCT06',
            number='002',
            model_name='Custom Mustang',
            year=2022,
            category='Mainline',
            series='HW Dream Garage',
            series_number='2/5',
            photo_url='https://example.com/mustang.jpg',
        )
        CollectionItem.objects.create(collection=self.public_collection, model=self.model_obj)
        CollectionItem.objects.create(collection=self.public_collection, model=second_model)

        response = self.client.get(
            reverse('collections:collection-detail', args=[self.public_collection.pk]),
            {'q': 'Mustang'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Custom Mustang')
        self.assertNotContains(response, '1970 Pontiac Firebird')
        self.assertContains(response, 'Znaleziono 1 pozycji')

    def test_collection_detail_shows_model_year_and_category(self):
        CollectionItem.objects.create(collection=self.public_collection, model=self.model_obj)

        response = self.client.get(reverse('collections:collection-detail', args=[self.public_collection.pk]))

        self.assertContains(response, 'Rok: 2022')
        self.assertContains(response, 'Kategoria: Mainline')
        self.assertContains(response, 'Statystyki i wykresy')
        self.assertContains(response, 'Roczniki')

    def test_collection_detail_groups_variants_for_same_model(self):
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
            is_sealed=True,
        )
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=2,
            condition='good',
            packaging_state='loose',
            is_signed=True,
        )

        response = self.client.get(reverse('collections:collection-detail', args=[self.public_collection.pk]))

        self.assertContains(response, 'Łącznie: 3 szt.')
        self.assertContains(response, 'Krótka karta | stan: Mint | ilość: 1')
        self.assertContains(response, 'Luzak | stan: Good | ilość: 2')
        self.assertContains(response, 'Cechy: Sealed')
        self.assertContains(response, 'Cechy: Signed')
        self.assertContains(response, '<strong>1</strong><div class="meta">pozycje</div>', html=False)
        self.assertContains(response, '<strong>2</strong><div class="meta">warianty</div>', html=False)

    def test_collection_detail_uses_packaging_specific_images(self):
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
        )
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=1,
            condition='good',
            packaging_state='loose',
        )

        response = self.client.get(reverse('collections:collection-detail', args=[self.public_collection.pk]))

        self.assertContains(response, 'https://example.com/short.jpg')
        self.assertContains(response, 'https://example.com/loose.jpg')

    def test_collection_detail_search_checks_series_and_toy_fields(self):
        CollectionItem.objects.create(collection=self.public_collection, model=self.model_obj)

        response = self.client.get(
            reverse('collections:collection-detail', args=[self.public_collection.pk]),
            {'q': 'HCT05'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1970 Pontiac Firebird')

    def test_collection_detail_can_filter_by_condition_and_packaging(self):
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
        )
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=2,
            condition='good',
            packaging_state='loose',
        )

        response = self.client.get(
            reverse('collections:collection-detail', args=[self.public_collection.pk]),
            {'condition': 'good', 'packaging': 'loose'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Luzak | stan: Good | ilość: 2')
        self.assertNotContains(response, 'Krótka karta | stan: Mint | ilość: 1')

    def test_collection_detail_can_filter_by_brand(self):
        second_model = HotWheelsModel.objects.create(
            app_id='def456',
            brand='Matchbox',
            toy='MBX01',
            number='002',
            model_name='MBX Adventure',
            year=2023,
            category='Mainline',
            series='Adventure Drivers',
            series_number='2/5',
            photo_url='https://example.com/matchbox.jpg',
        )
        CollectionItem.objects.create(collection=self.public_collection, model=self.model_obj)
        CollectionItem.objects.create(collection=self.public_collection, model=second_model)

        response = self.client.get(
            reverse('collections:collection-detail', args=[self.public_collection.pk]),
            {'brand': 'Hot Wheels'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertNotContains(response, 'MBX Adventure')

    def test_owner_can_export_collection_as_csv(self):
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj, quantity=2, is_favorite=True)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('collections:collection-export', args=[self.private_collection.pk, 'csv']))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('1970 Pontiac Firebird', response.content.decode())

    def test_owner_can_export_collection_as_json(self):
        CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=2,
            is_favorite=True,
            is_sealed=True,
            has_protector=True,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse('collections:collection-export', args=[self.private_collection.pk, 'json']))
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['collection']['name'], 'Prywatna')
        self.assertEqual(payload['items'][0]['model_name'], '1970 Pontiac Firebird')
        self.assertTrue(payload['items'][0]['is_sealed'])
        self.assertTrue(payload['items'][0]['has_protector'])

    def test_other_user_cannot_export_collection(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('collections:collection-export', args=[self.private_collection.pk, 'csv']))
        self.assertEqual(response.status_code, 404)

    def test_owner_can_batch_add_models_from_catalog(self):
        second_model = HotWheelsModel.objects.create(
            app_id='def456',
            toy='HCT06',
            number='002',
            model_name='Custom Mustang',
            year=2022,
            category='Mainline',
            series='HW Dream Garage',
            series_number='2/5',
            photo_url='https://example.com/mustang.jpg',
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('collections:batch-add'),
            {
                'collection': self.private_collection.pk,
                'model_ids': [self.model_obj.pk, second_model.pk],
                'next': reverse('catalog:model-list'),
            },
        )
        self.assertRedirects(response, reverse('catalog:model-list'))
        self.assertEqual(CollectionItem.objects.filter(collection=self.private_collection).count(), 2)

    def test_batch_add_skips_existing_models(self):
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj)
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('collections:batch-add'),
            {
                'collection': self.private_collection.pk,
                'model_ids': [self.model_obj.pk],
                'next': reverse('catalog:model-list'),
            },
        )
        self.assertRedirects(response, reverse('catalog:model-list'))
        self.assertEqual(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj).count(), 1)

    def test_owner_can_quick_add_model_variants_from_catalog(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:quick-add'),
            {
                'collection': self.private_collection.pk,
                'model': self.model_obj.pk,
                'next': reverse('catalog:model-list'),
                'enabled_short_card': 'on',
                'quantity_short_card': 1,
                'condition_short_card': 'mint',
                'is_sealed_short_card': 'on',
                'enabled_loose': 'on',
                'quantity_loose': 2,
                'condition_loose': 'good',
                'is_signed_loose': 'on',
            },
        )

        self.assertRedirects(response, reverse('catalog:model-list'))
        self.assertEqual(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj).count(), 2)
        self.assertTrue(CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj, packaging_state='short_card').is_sealed)
        self.assertTrue(CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj, packaging_state='loose').is_signed)

    def test_owner_can_batch_edit_selected_variants(self):
        short_card = CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
        )
        loose = CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=2,
            condition='good',
            packaging_state='loose',
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-batch-edit', args=[self.private_collection.pk]),
            {
                'item_ids': [short_card.pk, loose.pk],
                'quantity': 3,
                'condition': 'used',
                'packaging_state': '',
                'has_protector': 'true',
            },
        )

        self.assertRedirects(response, self.private_collection.get_absolute_url())
        short_card.refresh_from_db()
        loose.refresh_from_db()
        self.assertEqual(short_card.quantity, 3)
        self.assertEqual(loose.quantity, 3)
        self.assertEqual(short_card.condition, 'used')
        self.assertEqual(loose.condition, 'used')
        self.assertTrue(short_card.has_protector)
        self.assertTrue(loose.has_protector)

    def test_collection_detail_can_save_and_apply_filters(self):
        matchbox_model = HotWheelsModel.objects.create(
            app_id='def456',
            brand='Matchbox',
            toy='MBX01',
            number='002',
            model_name='MBX Adventure',
            year=2023,
            category='Mainline',
            series='Adventure Drivers',
            series_number='2/5',
            photo_url='https://example.com/matchbox.jpg',
        )
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj)
        CollectionItem.objects.create(collection=self.private_collection, model=matchbox_model)
        self.client.force_login(self.owner)

        save_response = self.client.get(
            reverse('collections:collection-detail', args=[self.private_collection.pk]),
            {'brand': 'Matchbox', 'save_filters': '1'},
        )
        self.assertRedirects(save_response, f'{self.private_collection.get_absolute_url()}?brand=Matchbox')

        apply_response = self.client.get(
            reverse('collections:collection-detail', args=[self.private_collection.pk]),
            {'apply_saved_filters': '1'},
        )
        self.assertRedirects(apply_response, f'{self.private_collection.get_absolute_url()}?brand=Matchbox')

    def test_owner_can_batch_delete_selected_variants(self):
        short_card = CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
        )
        CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=2,
            condition='good',
            packaging_state='loose',
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-batch-delete', args=[self.private_collection.pk]),
            {'item_ids': [short_card.pk]},
        )

        self.assertRedirects(response, self.private_collection.get_absolute_url())
        self.assertEqual(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj).count(), 1)

    def test_owner_can_batch_delete_all_variants_for_selected_model(self):
        CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
        )
        CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=2,
            condition='good',
            packaging_state='loose',
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-batch-delete', args=[self.private_collection.pk]),
            {'model_ids': [self.model_obj.pk]},
        )

        self.assertRedirects(response, self.private_collection.get_absolute_url())
        self.assertFalse(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj).exists())
