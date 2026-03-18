import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .management.commands.import_models import Command
from .models import HotWheelsModel


class ImportModelsCommandTests(TestCase):
    def test_clean_series_removes_new_for_2022_marker(self):
        self.assertEqual(
            Command.clean_series("HW MetroNew for 2022!Ryu's Rides"),
            "HW Metro Ryu's Rides",
        )

    def test_build_app_id_does_not_change_when_year_or_category_changes(self):
        row = {
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A',
            'Series Number': '1/5',
        }
        with_meta = {
            **row,
            'Year': '2023',
            'Category': 'Premium',
        }

        self.assertEqual(Command.build_app_id(row), Command.build_app_id(with_meta))

    def test_import_is_idempotent(self):
        payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A',
            'Series Number': '1/5',
            'Photo': 'https://example.com/car.jpg',
            'Local Photo': 'images/car.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))
            call_command('import_models', path=str(path))

        self.assertEqual(HotWheelsModel.objects.count(), 1)

    def test_import_backfills_packaging_photos_from_default_photo(self):
        payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A',
            'Series Number': '1/5',
            'Photo': 'https://example.com/car.jpg',
            'Local Photo': 'images/car.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.short_card_photo_url, 'https://example.com/car.jpg')
        self.assertEqual(model.long_card_photo_url, 'https://example.com/car.jpg')
        self.assertEqual(model.loose_photo_url, 'https://example.com/car.jpg')
        self.assertEqual(model.short_card_local_photo_path, 'images/car.jpg')
        self.assertEqual(model.long_card_local_photo_path, 'images/car.jpg')
        self.assertEqual(model.loose_local_photo_path, 'images/car.jpg')

    def test_import_handles_null_local_photo_paths(self):
        payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A',
            'Series Number': '1/5',
            'Photo': None,
            'Local Photo': None,
            'Short Card Photo': None,
            'Short Card Local Photo': None,
            'Long Card Photo': None,
            'Long Card Local Photo': None,
            'Loose Photo': None,
            'Loose Local Photo': None,
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.photo_url, '')
        self.assertEqual(model.local_photo_path, '')
        self.assertEqual(model.short_card_photo_url, '')
        self.assertEqual(model.short_card_local_photo_path, '')
        self.assertEqual(model.long_card_photo_url, '')
        self.assertEqual(model.long_card_local_photo_path, '')
        self.assertEqual(model.loose_photo_url, '')
        self.assertEqual(model.loose_local_photo_path, '')

    def test_import_sets_year_and_category(self):
        payload = [{
            'Brand': 'Matchbox',
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A New for 2023!',
            'Series Number': '1/5',
            'Photo': 'https://example.com/car.jpg',
            'Local Photo': 'images/car.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.brand, 'Matchbox')
        self.assertEqual(model.year, 2023)
        self.assertEqual(model.category, 'Mainline')
        self.assertEqual(model.series, 'Series A')

    def test_import_can_read_brand_line_and_year_from_path_structure(self):
        payload = [{
            'Toy': 'MBX01',
            'Number': '002',
            'Model Name': 'Adventure Van',
            'Series': 'Adventure Drivers',
            'Series Number': '2/5',
            'Photo': 'https://example.com/van.jpg',
            'Local Photo': 'images/van.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'matchbox' / 'collectors' / '2024.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.brand, 'Matchbox')
        self.assertEqual(model.category, 'Collectors')
        self.assertEqual(model.year, 2024)

    def test_import_can_scan_dataset_tree(self):
        first_payload = [{
            'Brand': 'Hot Wheels',
            'Category': 'Mainline',
            'Year': 2022,
            'Toy': 'HW01',
            'Number': '001',
            'Model Name': 'Car One',
            'Series': 'Series A',
            'Series Number': '1/5',
        }]
        second_payload = [{
            'Toy': 'MBX01',
            'Number': '002',
            'Model Name': 'Car Two',
            'Series': 'Series B',
            'Series Number': '2/5',
        }]

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first_path = root / 'hot-wheels' / 'mainline' / '2022.json'
            second_path = root / 'matchbox' / 'collectors' / '2024.json'
            first_path.parent.mkdir(parents=True, exist_ok=True)
            second_path.parent.mkdir(parents=True, exist_ok=True)
            first_path.write_text(json.dumps(first_payload))
            second_path.write_text(json.dumps(second_payload))

            call_command('import_models', root=str(root))

        self.assertEqual(HotWheelsModel.objects.count(), 2)
        self.assertTrue(HotWheelsModel.objects.filter(model_name='Car One', brand='Hot Wheels').exists())
        self.assertTrue(HotWheelsModel.objects.filter(model_name='Car Two', brand='Matchbox', category='Collectors').exists())

    def test_import_can_filter_dataset_tree(self):
        hot_wheels_payload = [{
            'Toy': 'HW01',
            'Number': '001',
            'Model Name': 'Car One',
            'Series': 'Series A',
            'Series Number': '1/5',
        }]
        matchbox_payload = [{
            'Toy': 'MBX01',
            'Number': '002',
            'Model Name': 'Car Two',
            'Series': 'Series B',
            'Series Number': '2/5',
        }]

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hot_wheels_path = root / 'hot-wheels' / 'mainline' / '2022.json'
            matchbox_path = root / 'matchbox' / 'collectors' / '2024.json'
            hot_wheels_path.parent.mkdir(parents=True, exist_ok=True)
            matchbox_path.parent.mkdir(parents=True, exist_ok=True)
            hot_wheels_path.write_text(json.dumps(hot_wheels_payload))
            matchbox_path.write_text(json.dumps(matchbox_payload))

            call_command('import_models', root=str(root), brand='matchbox', line='collectors', year=2024)

        self.assertEqual(HotWheelsModel.objects.count(), 1)
        model = HotWheelsModel.objects.get()
        self.assertEqual(model.brand, 'Matchbox')
        self.assertEqual(model.category, 'Collectors')
        self.assertEqual(model.year, 2024)

    def test_import_cleans_new_for_2022_marker_from_series(self):
        payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': "HW MetroNew for 2022!Ryu's Rides",
            'Series Number': '1/5',
            'Photo': 'https://example.com/car.jpg',
            'Local Photo': 'images/car.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.series, "HW Metro Ryu's Rides")

    def test_import_cleans_new_for_2023_marker_from_series(self):
        payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'HW Dream GarageNew for 2023!Target Exclusive',
            'Series Number': '1/5',
            'Photo': 'https://example.com/car.jpg',
            'Local Photo': 'images/car.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.series, 'HW Dream Garage Target Exclusive')


class CatalogViewTests(TestCase):
    def setUp(self):
        self.model_obj = HotWheelsModel.objects.create(
            app_id='abc123',
            brand='Hot Wheels',
            toy='HCT05',
            number='001',
            model_name='1970 Pontiac Firebird',
            year=2022,
            category='Mainline',
            series='HW Dream Garage',
            series_number='1/5',
            photo_url='https://example.com/car.jpg',
        )

    def test_catalog_uses_packaging_variant_order_for_card_image(self):
        self.model_obj.short_card_photo_url = ''
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        response = self.client.get(reverse('catalog:model-list'))

        self.assertContains(response, 'https://example.com/long.jpg')
        self.assertContains(response, 'data-image-label="Długa"')
        self.assertContains(response, 'data-image-label="Luzak"')

    def test_catalog_model_exposes_packaging_variants(self):
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = ''
        self.model_obj.save(update_fields=['short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['short_card', 'long_card'])
        self.assertEqual(self.model_obj.catalog_primary_image_src, 'https://example.com/short.jpg')

    def test_catalog_search(self):
        response = self.client.get(reverse('catalog:model-list'), {'q': 'Firebird'})
        self.assertContains(response, '1970 Pontiac Firebird')

    def test_catalog_can_filter_by_year_and_category(self):
        HotWheelsModel.objects.create(
            app_id='def456',
            brand='Matchbox',
            toy='HCT06',
            number='002',
            model_name='Custom Mustang',
            year=2023,
            category='Premium',
            series='HW Dream Garage',
            series_number='2/5',
            photo_url='https://example.com/mustang.jpg',
        )

        response = self.client.get(reverse('catalog:model-list'), {'year': '2022', 'category': 'Mainline'})

        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertNotContains(response, 'Custom Mustang')

    def test_catalog_can_filter_by_brand(self):
        HotWheelsModel.objects.create(
            app_id='def456',
            brand='Matchbox',
            toy='HCT06',
            number='002',
            model_name='Custom Mustang',
            year=2023,
            category='Premium',
            series='MBX Road Trip',
            series_number='2/5',
            photo_url='https://example.com/mustang.jpg',
        )

        response = self.client.get(reverse('catalog:model-list'), {'brand': 'Hot Wheels'})

        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertNotContains(response, 'Custom Mustang')

    def test_catalog_can_save_and_apply_filters(self):
        save_response = self.client.get(
            reverse('catalog:model-list'),
            {'brand': 'Hot Wheels', 'sort': 'name', 'save_filters': '1'},
        )
        self.assertRedirects(save_response, f"{reverse('catalog:model-list')}?brand=Hot+Wheels&sort=name")

        apply_response = self.client.get(reverse('catalog:model-list'), {'apply_saved_filters': '1'})
        self.assertRedirects(apply_response, f"{reverse('catalog:model-list')}?brand=Hot+Wheels&sort=name")

    def test_model_detail(self):
        response = self.client.get(reverse('catalog:model-detail', args=[self.model_obj.pk]))
        self.assertContains(response, 'HCT05')
        self.assertContains(response, 'Hot Wheels')
        self.assertContains(response, '2022')
        self.assertContains(response, 'Mainline')
        self.assertContains(response, 'Krótka karta')
        self.assertContains(response, 'Długa karta')
        self.assertContains(response, 'Luzak')

    def test_healthcheck(self):
        response = self.client.get(reverse('healthcheck'))
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'status': 'ok'})
