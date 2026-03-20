from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
import json

from accounts.models import User
from catalog.models import HotWheelsModel

from .models import Collection, CollectionItem, ImportBacklogEntry, ImportBacklogReport


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

    def test_item_create_marks_loose_variant_as_without_card_attributes(self):
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {'model': self.model_obj.pk},
        )

        loose_section = next(
            section for section in response.context['form'].variant_sections if section['packaging_value'] == 'loose'
        )
        self.assertFalse(loose_section['supports_card_attributes'])

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

    def test_loose_variant_clears_card_attributes_from_post_data(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': self.model_obj.pk,
                'enabled_loose': 'on',
                'quantity_loose': 1,
                'condition_loose': 'good',
                'is_sealed_loose': 'on',
                'has_protector_loose': 'on',
                'has_bent_hook_loose': 'on',
                'has_cracked_blister_loose': 'on',
            },
        )

        self.assertRedirects(response, self.private_collection.get_absolute_url())
        item = CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj, packaging_state='loose')
        self.assertFalse(item.is_sealed)
        self.assertFalse(item.has_protector)
        self.assertFalse(item.has_bent_hook)
        self.assertFalse(item.has_cracked_blister)

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

    def test_owner_can_add_same_model_with_bent_hook_difference(self):
        CollectionItem.objects.create(
            collection=self.private_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
            has_bent_hook=True,
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': self.model_obj.pk,
                'enabled_short_card': 'on',
                'quantity_short_card': 1,
                'condition_short_card': 'mint',
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

    def test_rlc_item_form_hides_short_card_option(self):
        rlc_model = HotWheelsModel.objects.create(
            app_id='rlc123',
            toy='HWF03',
            number='HWF03',
            model_name='Kawa-Bug-A',
            brand='Hot Wheels',
            year=2024,
            category='RLC',
            series='2024 RLC Exclusive',
            series_number='',
            photo_url='https://example.com/kawa.jpg',
            long_card_photo_url='https://example.com/kawa-carded.jpg',
            loose_photo_url='https://example.com/kawa-loose.jpg',
        )
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {'model': rlc_model.pk},
        )

        self.assertNotContains(response, 'Krótka karta')
        self.assertContains(response, 'Długa')
        self.assertContains(response, 'Luzak')

    def test_exclusive_item_form_hides_short_card_option(self):
        exclusive_model = HotWheelsModel.objects.create(
            app_id='exclusive123',
            toy='ABC01',
            number='001',
            model_name='Exclusive Car',
            brand='Hot Wheels',
            year=2024,
            category='Mainline',
            series='HW Metro',
            exclusive_store='Walmart Exclusive',
            series_number='1/5',
            photo_url='https://example.com/exclusive.jpg',
            long_card_photo_url='https://example.com/exclusive-carded.jpg',
            loose_photo_url='https://example.com/exclusive-loose.jpg',
        )
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {'model': exclusive_model.pk},
        )

        self.assertNotContains(response, 'Krótka karta')
        self.assertContains(response, 'Długa')
        self.assertContains(response, 'Luzak')

    def test_owner_cannot_add_rlc_as_short_card(self):
        rlc_model = HotWheelsModel.objects.create(
            app_id='rlc124',
            toy='HWF04',
            number='HWF04',
            model_name='1993 Mazda RX-7 R1',
            brand='Hot Wheels',
            year=2024,
            category='RLC',
            series='2024 RLC Exclusive',
            series_number='',
            photo_url='https://example.com/rx7.jpg',
            long_card_photo_url='https://example.com/rx7-carded.jpg',
            loose_photo_url='https://example.com/rx7-loose.jpg',
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': rlc_model.pk,
                'enabled_short_card': 'on',
                'quantity_short_card': 1,
                'condition_short_card': 'mint',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Zaznacz przynajmniej jeden wariant modelu do dodania.')
        self.assertNotContains(response, 'Krótka karta')
        self.assertFalse(CollectionItem.objects.filter(collection=self.private_collection, model=rlc_model).exists())

    def test_owner_cannot_add_exclusive_as_short_card(self):
        exclusive_model = HotWheelsModel.objects.create(
            app_id='exclusive124',
            toy='ABC02',
            number='002',
            model_name='Exclusive Car 2',
            brand='Hot Wheels',
            year=2024,
            category='Mainline',
            series='HW Metro',
            exclusive_store='Target Exclusive',
            series_number='2/5',
            photo_url='https://example.com/exclusive2.jpg',
            long_card_photo_url='https://example.com/exclusive2-carded.jpg',
            loose_photo_url='https://example.com/exclusive2-loose.jpg',
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('collections:item-create', args=[self.private_collection.pk]),
            {
                'model': exclusive_model.pk,
                'enabled_short_card': 'on',
                'quantity_short_card': 1,
                'condition_short_card': 'mint',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Zaznacz przynajmniej jeden wariant modelu do dodania.')
        self.assertNotContains(response, 'Krótka karta')
        self.assertFalse(CollectionItem.objects.filter(collection=self.private_collection, model=exclusive_model).exists())

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
        self.assertContains(response, 'Otwórz statystyki')
        self.assertContains(response, 'Importuj CSV')
        self.assertContains(response, 'Braki z importów')
        self.assertNotContains(response, 'Statystyki i wykresy')

    def test_collection_import_preview_matches_rows_from_csv(self):
        self.client.force_login(self.owner)
        payload = (
            'ID,Name,Color,Year,Type,Series,Series Number,Price,Amount,Where\n'
            '1,1970 Pontiac Firebird,Black,2022,Mainline,HW Dream Garage,1/5,20 zl,2,Shelf A\n'
        )

        response = self.client.post(
            reverse('collections:collection-import'),
            {
                'collection': self.private_collection.pk,
                'new_collection_name': '',
                'new_collection_kind': Collection.KIND_OWNED,
                'new_collection_visibility': Collection.VISIBILITY_PRIVATE,
                'default_condition': 'good',
                'import_mode': 'merge',
                'append_price_to_notes': 'on',
                'append_location_to_notes': 'on',
                'source_file': SimpleUploadedFile('collection.csv', payload.encode('utf-8'), content_type='text/csv'),
            },
        )

        self.assertEqual(response.status_code, 302)
        preview_response = self.client.get(response['Location'])
        self.assertContains(preview_response, 'Podgląd importu')
        self.assertContains(preview_response, 'Dopasowane')
        self.assertContains(preview_response, '1970 Pontiac Firebird')
        self.assertContains(preview_response, 'matched')

    def test_collection_import_confirm_creates_items_and_notes(self):
        self.client.force_login(self.owner)
        payload = (
            'ID,Name,Color,Year,Type,Series,Series Number,Price,Amount,Where\n'
            '1,1970 Pontiac Firebird,Black,2022,Mainline,HW Dream Garage,1/5,20 zl,2,Shelf A\n'
        )

        preview_response = self.client.post(
            reverse('collections:collection-import'),
            {
                'collection': self.private_collection.pk,
                'new_collection_name': '',
                'new_collection_kind': Collection.KIND_OWNED,
                'new_collection_visibility': Collection.VISIBILITY_PRIVATE,
                'default_condition': 'good',
                'import_mode': 'merge',
                'append_price_to_notes': 'on',
                'append_location_to_notes': 'on',
                'source_file': SimpleUploadedFile('collection.csv', payload.encode('utf-8'), content_type='text/csv'),
            },
        )
        preview_page = self.client.get(preview_response['Location'])
        token = preview_page.context['preview_token']

        response = self.client.post(
            reverse('collections:collection-import-confirm'),
            {'preview_token': token},
        )

        self.assertRedirects(response, self.private_collection.get_absolute_url())
        item = CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj)
        self.assertEqual(item.quantity, 2)
        self.assertIn('Imported price: 20 zl', item.notes)
        self.assertIn('Imported location: Shelf A', item.notes)

    def test_collection_import_preview_records_unmatched_backlog_entry(self):
        self.client.force_login(self.owner)
        payload = (
            'ID,Name,Color,Year,Type,Series,Series Number,Price,Amount,Where\n'
            '1,Unreleased Civic,Black,2026,Premium,Future Series,1/5,50 zl,1,Box B\n'
        )

        response = self.client.post(
            reverse('collections:collection-import'),
            {
                'collection': self.private_collection.pk,
                'new_collection_name': '',
                'new_collection_kind': Collection.KIND_OWNED,
                'new_collection_visibility': Collection.VISIBILITY_PRIVATE,
                'default_condition': 'good',
                'import_mode': 'merge',
                'append_price_to_notes': 'on',
                'append_location_to_notes': 'on',
                'source_file': SimpleUploadedFile('collection.csv', payload.encode('utf-8'), content_type='text/csv'),
            },
        )

        self.assertEqual(response.status_code, 302)
        entry = ImportBacklogEntry.objects.get(model_name='Unreleased Civic')
        self.assertEqual(entry.status, ImportBacklogEntry.STATUS_OPEN)
        self.assertEqual(entry.report_count, 1)
        self.assertEqual(entry.category, 'Premium')
        self.assertEqual(entry.series, 'Future Series')
        report = ImportBacklogReport.objects.get(backlog_entry=entry, owner=self.owner)
        self.assertEqual(report.collection, self.private_collection)
        self.assertEqual(report.import_count, 1)
        self.assertEqual(report.location, 'Box B')

    def test_collection_import_merge_mode_adds_quantity_to_existing_item(self):
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj, quantity=2, condition='good')
        self.client.force_login(self.owner)
        payload = (
            'ID,Name,Year,Type,Series,Series Number,Amount\n'
            '1,1970 Pontiac Firebird,2022,Mainline,HW Dream Garage,1/5,3\n'
        )

        preview_response = self.client.post(
            reverse('collections:collection-import'),
            {
                'collection': self.private_collection.pk,
                'new_collection_name': '',
                'new_collection_kind': Collection.KIND_OWNED,
                'new_collection_visibility': Collection.VISIBILITY_PRIVATE,
                'default_condition': 'good',
                'import_mode': 'merge',
                'source_file': SimpleUploadedFile('collection.csv', payload.encode('utf-8'), content_type='text/csv'),
            },
        )
        preview_page = self.client.get(preview_response['Location'])
        token = preview_page.context['preview_token']

        self.client.post(reverse('collections:collection-import-confirm'), {'preview_token': token})

        item = CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj, condition='good')
        self.assertEqual(item.quantity, 5)

    def test_collection_import_replace_mode_overwrites_existing_quantity(self):
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj, quantity=2, condition='good')
        self.client.force_login(self.owner)
        payload = (
            'ID,Name,Year,Type,Series,Series Number,Amount\n'
            '1,1970 Pontiac Firebird,2022,Mainline,HW Dream Garage,1/5,3\n'
        )

        preview_response = self.client.post(
            reverse('collections:collection-import'),
            {
                'collection': self.private_collection.pk,
                'new_collection_name': '',
                'new_collection_kind': Collection.KIND_OWNED,
                'new_collection_visibility': Collection.VISIBILITY_PRIVATE,
                'default_condition': 'good',
                'import_mode': 'replace',
                'source_file': SimpleUploadedFile('collection.csv', payload.encode('utf-8'), content_type='text/csv'),
            },
        )
        preview_page = self.client.get(preview_response['Location'])
        token = preview_page.context['preview_token']

        self.client.post(reverse('collections:collection-import-confirm'), {'preview_token': token})

        item = CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj, condition='good')
        self.assertEqual(item.quantity, 3)

    def test_collection_import_skip_mode_leaves_existing_quantity_unchanged(self):
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj, quantity=2, condition='good')
        self.client.force_login(self.owner)
        payload = (
            'ID,Name,Year,Type,Series,Series Number,Amount\n'
            '1,1970 Pontiac Firebird,2022,Mainline,HW Dream Garage,1/5,3\n'
        )

        preview_response = self.client.post(
            reverse('collections:collection-import'),
            {
                'collection': self.private_collection.pk,
                'new_collection_name': '',
                'new_collection_kind': Collection.KIND_OWNED,
                'new_collection_visibility': Collection.VISIBILITY_PRIVATE,
                'default_condition': 'good',
                'import_mode': 'skip',
                'source_file': SimpleUploadedFile('collection.csv', payload.encode('utf-8'), content_type='text/csv'),
            },
        )
        preview_page = self.client.get(preview_response['Location'])
        token = preview_page.context['preview_token']

        self.client.post(reverse('collections:collection-import-confirm'), {'preview_token': token})

        item = CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj, condition='good')
        self.assertEqual(item.quantity, 2)

    def test_import_backlog_view_lists_unmatched_models(self):
        entry = ImportBacklogEntry.objects.create(
            model_name='Unreleased Civic',
            year=2026,
            category='Premium',
            series='Future Series',
            series_number='1/5',
        )
        ImportBacklogReport.objects.create(
            backlog_entry=entry,
            owner=self.owner,
            collection=self.private_collection,
            location='Box B',
        )
        self.client.force_login(self.owner)

        response = self.client.get(reverse('collections:import-backlog'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Braki z importów')
        self.assertContains(response, 'Unreleased Civic')
        self.assertContains(response, 'Future Series')
        self.assertContains(response, 'Zgłoszeń: 1')

    def test_import_backlog_aggregates_same_model_across_users(self):
        other_collection = Collection.objects.create(
            owner=self.other,
            name='Other backlog source',
            kind=Collection.KIND_OWNED,
            visibility=Collection.VISIBILITY_PRIVATE,
        )
        payload = {
            'toy': '',
            'model_name': 'Unreleased Civic',
            'year': 2026,
            'category': 'Premium',
            'series': 'Future Series',
            'series_number': '1/5',
            'color': 'Red',
            'price': '50 zl',
            'location': 'Box A',
        }
        from .views import record_import_backlog

        record_import_backlog(self.owner, self.private_collection, payload)
        record_import_backlog(self.other, other_collection, {**payload, 'color': 'Dark Red', 'location': 'Box B'})

        entry = ImportBacklogEntry.objects.get(model_name='Unreleased Civic')
        self.assertEqual(ImportBacklogEntry.objects.count(), 1)
        self.assertEqual(entry.report_count, 2)
        self.assertEqual(entry.reports.count(), 2)

    def test_stats_page_shows_charts(self):
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj, quantity=3, is_favorite=True)
        self.client.force_login(self.owner)

        response = self.client.get(reverse('collections:stats'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Moje statystyki')
        self.assertContains(response, 'Przegląd completion')
        self.assertContains(response, 'Po rocznikach')
        self.assertContains(response, 'Po seriach')
        self.assertContains(response, 'Posiadane: 1 / 1')
        self.assertNotContains(response, 'Missing Models')
        self.assertNotContains(response, 'Brakujące modele')

    def test_stats_page_does_not_show_global_missing_model_list(self):
        second_model = HotWheelsModel.objects.create(
            app_id='def456',
            toy='HCT06',
            number='002',
            model_name='Custom Mustang',
            year=2023,
            category='Mainline',
            series='HW Dream Garage',
            series_number='2/5',
            photo_url='https://example.com/mustang.jpg',
        )
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj, quantity=1)
        self.client.force_login(self.owner)

        response = self.client.get(reverse('collections:stats'))

        self.assertNotContains(response, 'Custom Mustang')
        self.assertContains(response, 'Posiadane: 1 / 2')

    def test_collection_detail_shows_owner_profile_link(self):
        response = self.client.get(reverse('collections:collection-detail', args=[self.public_collection.pk]))
        self.assertContains(response, reverse('accounts:public-profile', args=[self.owner.pk]))

    def test_public_collection_list_redirects_to_community(self):
        response = self.client.get(reverse('collections:public-collections'))
        self.assertRedirects(response, f"{reverse('collections:community')}?view=collections")

    def test_community_page_shows_public_collections(self):
        response = self.client.get(reverse('collections:community'))
        self.assertContains(response, 'Publiczna')
        self.assertNotContains(response, 'Prywatna')
        self.assertContains(response, 'Społeczność')

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
        self.assertNotContains(response, 'Statystyki i wykresy')

    def test_owner_collection_detail_shows_stats_link(self):
        CollectionItem.objects.create(collection=self.private_collection, model=self.model_obj)
        self.client.force_login(self.owner)

        response = self.client.get(reverse('collections:collection-detail', args=[self.private_collection.pk]))

        self.assertContains(response, 'Statystyki tej kolekcji')

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

    def test_collection_detail_can_filter_by_packaging_attributes(self):
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
            is_sealed=True,
            has_protector=True,
        )
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=2,
            condition='good',
            packaging_state='loose',
            is_signed=True,
        )

        response = self.client.get(
            reverse('collections:collection-detail', args=[self.public_collection.pk]),
            {'sealed': 'yes', 'protector': 'yes'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Krótka karta | stan: Mint | ilość: 1')
        self.assertContains(response, 'Cechy: Sealed, Protector')
        self.assertNotContains(response, 'Luzak | stan: Good | ilość: 2')

    def test_collection_detail_can_filter_by_bent_hook_and_cracked_blister(self):
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
            has_bent_hook=True,
        )
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=2,
            condition='good',
            packaging_state='long_card',
            has_cracked_blister=True,
        )

        response = self.client.get(
            reverse('collections:collection-detail', args=[self.public_collection.pk]),
            {'cracked_blister': 'yes'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Długa karta | stan: Good | ilość: 2')
        self.assertContains(response, 'Cechy: Cracked blister')
        self.assertNotContains(response, 'Krótka karta | stan: Mint | ilość: 1')

    def test_collection_detail_can_filter_for_missing_packaging_attribute(self):
        CollectionItem.objects.create(
            collection=self.public_collection,
            model=self.model_obj,
            quantity=1,
            condition='mint',
            packaging_state='short_card',
            has_soft_corners=True,
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
            {'soft_corners': 'no'},
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
            has_bent_hook=True,
        )
        self.client.force_login(self.owner)
        response = self.client.get(reverse('collections:collection-export', args=[self.private_collection.pk, 'json']))
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode())
        self.assertEqual(payload['collection']['name'], 'Prywatna')
        self.assertEqual(payload['items'][0]['model_name'], '1970 Pontiac Firebird')
        self.assertTrue(payload['items'][0]['is_sealed'])
        self.assertTrue(payload['items'][0]['has_protector'])
        self.assertTrue(payload['items'][0]['has_bent_hook'])

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
                'has_bent_hook_short_card': 'on',
                'enabled_loose': 'on',
                'quantity_loose': 2,
                'condition_loose': 'good',
                'is_signed_loose': 'on',
                'has_cracked_blister_loose': 'on',
            },
        )

        self.assertRedirects(response, reverse('catalog:model-list'))
        self.assertEqual(CollectionItem.objects.filter(collection=self.private_collection, model=self.model_obj).count(), 2)
        self.assertTrue(CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj, packaging_state='short_card').is_sealed)
        self.assertTrue(CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj, packaging_state='short_card').has_bent_hook)
        self.assertFalse(CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj, packaging_state='loose').is_signed)
        self.assertFalse(CollectionItem.objects.get(collection=self.private_collection, model=self.model_obj, packaging_state='loose').has_cracked_blister)

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
                'has_cracked_blister': 'true',
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
        self.assertFalse(loose.has_protector)
        self.assertTrue(short_card.has_cracked_blister)
        self.assertFalse(loose.has_cracked_blister)

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
            {'brand': 'Matchbox', 'sealed': 'yes', 'cracked_blister': 'no', 'save_filters': '1'},
        )
        self.assertRedirects(save_response, f'{self.private_collection.get_absolute_url()}?brand=Matchbox&sealed=yes&cracked_blister=no')

        apply_response = self.client.get(
            reverse('collections:collection-detail', args=[self.private_collection.pk]),
            {'apply_saved_filters': '1'},
        )
        self.assertRedirects(apply_response, f'{self.private_collection.get_absolute_url()}?brand=Matchbox&sealed=yes&cracked_blister=no')

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
