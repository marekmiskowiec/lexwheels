import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from collections_app.models import Collection, CollectionItem

from .management.commands.import_models import Command
from .models import HotWheelsModel


class ImportModelsCommandTests(TestCase):
    def test_clean_series_removes_new_for_marker(self):
        self.assertEqual(
            Command.clean_series("HW MetroNew for 2022!Ryu's Rides"),
            "HW Metro Ryu's Rides",
        )
        self.assertEqual(
            Command.clean_series("Drop TopsNew for 2026!"),
            "Drop Tops",
        )

    def test_build_app_id_ignores_new_for_marker_in_series(self):
        dirty_row = {
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A New for 2024!',
            'Series Number': '1/5',
        }
        clean_row = {
            **dirty_row,
            'Series': 'Series A',
        }
        self.assertEqual(Command.build_app_id(dirty_row), Command.build_app_id(clean_row))

    def test_parse_series_metadata_extracts_store_exclusive(self):
        parsed = Command.parse_series_metadata('Chevy Bel AirDollar General Exclusive')
        self.assertEqual(parsed['series'], 'Chevy Bel Air')
        self.assertEqual(parsed['exclusive_store'], 'Dollar General Exclusive')
        self.assertEqual(parsed['special_tag'], '')

    def test_parse_series_metadata_extracts_special_tag(self):
        parsed = Command.parse_series_metadata('Chevy Bel AirSuper Treasure Hunt')
        self.assertEqual(parsed['series'], 'Chevy Bel Air')
        self.assertEqual(parsed['exclusive_store'], '')
        self.assertEqual(parsed['special_tag'], 'Super Treasure Hunt')

    def test_parse_series_metadata_extracts_special_tag_and_store(self):
        parsed = Command.parse_series_metadata('Red EditionTarget Exclusive')
        self.assertEqual(parsed['series'], 'Red Edition')
        self.assertEqual(parsed['exclusive_store'], 'Target Exclusive')
        self.assertEqual(parsed['special_tag'], 'Red Edition')

    def test_parse_series_metadata_normalizes_reverse_family_dollar_marker(self):
        parsed = Command.parse_series_metadata('HW Reverse RakeFamily Dollar/Dollar Tree Exclusive')
        self.assertEqual(parsed['series'], 'HW Reverse Rake')
        self.assertEqual(parsed['exclusive_store'], 'Dollar Tree/Family Dollar Exclusive')
        self.assertEqual(parsed['special_tag'], '')

    def test_parse_series_metadata_extracts_best_buy_suffix_inside_series(self):
        parsed = Command.parse_series_metadata("HW MetroBest Buy ExclusiveRyu's Rides")
        self.assertEqual(parsed['series'], "HW Metro Ryu's Rides")
        self.assertEqual(parsed['exclusive_store'], 'Best Buy Exclusive')
        self.assertEqual(parsed['special_tag'], '')

    def test_parse_series_metadata_extracts_walgreens_without_space(self):
        parsed = Command.parse_series_metadata('Then and NowWalgreensExclusive')
        self.assertEqual(parsed['series'], 'Then and Now')
        self.assertEqual(parsed['exclusive_store'], 'Walgreens Exclusive')
        self.assertEqual(parsed['special_tag'], '')

    def test_parse_series_metadata_extracts_from_the_vault_as_special_tag(self):
        parsed = Command.parse_series_metadata('HW J-Imports"From the Vault" Exclusive')
        self.assertEqual(parsed['series'], 'HW J-Imports')
        self.assertEqual(parsed['exclusive_store'], '')
        self.assertEqual(parsed['special_tag'], 'From the Vault')

    def test_parse_series_metadata_discards_new_in_mainline(self):
        parsed = Command.parse_series_metadata('Compact KingsNew in Mainline')
        self.assertEqual(parsed['series'], 'Compact Kings')
        self.assertEqual(parsed['exclusive_store'], '')
        self.assertEqual(parsed['special_tag'], '')

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

    def test_import_does_not_backfill_short_card_for_semi_premium(self):
        payload = [{
            'Brand': 'Hot Wheels',
            'Category': 'Semi Premium',
            'Year': 2025,
            'Toy': 'HWFF01',
            'Number': '1/5',
            'Model Name': 'Toyota Supra',
            'Series': "Fast & Furious: Brian O'Conner Series",
            'Series Number': '1/5',
            'Photo': 'https://example.com/carded.jpg',
            'Local Photo': 'images/carded.jpg',
            'Short Card Photo': '',
            'Short Card Local Photo': '',
            'Long Card Photo': 'https://example.com/carded.jpg',
            'Long Card Local Photo': 'images/carded.jpg',
            'Loose Photo': 'https://example.com/loose.jpg',
            'Loose Local Photo': 'images/loose.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'hot-wheels' / 'semi-premium' / '2025' / 'brian.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.short_card_photo_url, '')
        self.assertEqual(model.short_card_local_photo_path, '')
        self.assertEqual(model.long_card_photo_url, 'https://example.com/carded.jpg')
        self.assertEqual(model.loose_photo_url, 'https://example.com/loose.jpg')

    def test_import_does_not_backfill_short_card_for_xl(self):
        payload = [{
            'Brand': 'Hot Wheels',
            'Category': 'XL',
            'Year': 2026,
            'Toy': 'JKL09',
            'Number': '1/24',
            'Model Name': 'Porsche 934.5',
            'Series': 'Hot Wheels XL',
            'Series Number': '1/24',
            'Photo': 'https://example.com/carded.jpg',
            'Local Photo': 'images/carded.jpg',
            'Short Card Photo': '',
            'Short Card Local Photo': '',
            'Long Card Photo': 'https://example.com/carded.jpg',
            'Long Card Local Photo': 'images/carded.jpg',
            'Loose Photo': 'https://example.com/open.jpg',
            'Loose Local Photo': 'images/open.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'hot-wheels' / 'xl' / '2026.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.short_card_photo_url, '')
        self.assertEqual(model.short_card_local_photo_path, '')
        self.assertEqual(model.long_card_photo_url, 'https://example.com/carded.jpg')
        self.assertEqual(model.loose_photo_url, 'https://example.com/open.jpg')

    def test_import_does_not_backfill_short_card_for_premium(self):
        payload = [{
            'Brand': 'Hot Wheels',
            'Category': 'Premium',
            'Year': 2023,
            'Toy': 'HP01',
            'Number': '1/5',
            'Model Name': 'Premium Test Car',
            'Series': 'Fast & Furious Premium Series - Mix 1',
            'Series Number': '1/5',
            'Photo': 'https://example.com/carded.jpg',
            'Local Photo': 'images/carded.jpg',
            'Short Card Photo': '',
            'Short Card Local Photo': '',
            'Long Card Photo': 'https://example.com/carded.jpg',
            'Long Card Local Photo': 'images/carded.jpg',
            'Loose Photo': 'https://example.com/open.jpg',
            'Loose Local Photo': 'images/open.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'hot-wheels' / 'premium' / '2023' / 'mix-1.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.short_card_photo_url, '')
        self.assertEqual(model.short_card_local_photo_path, '')
        self.assertEqual(model.long_card_photo_url, 'https://example.com/carded.jpg')
        self.assertEqual(model.loose_photo_url, 'https://example.com/open.jpg')

    def test_import_does_not_backfill_short_card_for_rlc(self):
        payload = [{
            'Brand': 'Hot Wheels',
            'Category': 'RLC',
            'Year': 2024,
            'Toy': 'HWF03',
            'Number': 'HWF03',
            'Model Name': 'Kawa-Bug-A',
            'Series': '2024 RLC Exclusive',
            'Series Number': '',
            'Photo': 'https://example.com/carded.jpg',
            'Local Photo': 'images/carded.jpg',
            'Short Card Photo': '',
            'Short Card Local Photo': '',
            'Long Card Photo': 'https://example.com/carded.jpg',
            'Long Card Local Photo': 'images/carded.jpg',
            'Loose Photo': 'https://example.com/loose.jpg',
            'Loose Local Photo': 'images/loose.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'hot-wheels' / 'rlc' / '2024.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.short_card_photo_url, '')
        self.assertEqual(model.short_card_local_photo_path, '')
        self.assertEqual(model.long_card_photo_url, 'https://example.com/carded.jpg')
        self.assertEqual(model.loose_photo_url, 'https://example.com/loose.jpg')

    def test_import_does_not_backfill_short_card_for_exclusive(self):
        payload = [{
            'Brand': 'Hot Wheels',
            'Category': 'Mainline',
            'Year': 2024,
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'HW MetroWalmart Exclusive',
            'Series Number': '1/5',
            'Photo': 'https://example.com/carded.jpg',
            'Local Photo': 'images/carded.jpg',
            'Short Card Photo': '',
            'Short Card Local Photo': '',
            'Long Card Photo': 'https://example.com/carded.jpg',
            'Long Card Local Photo': 'images/carded.jpg',
            'Loose Photo': 'https://example.com/loose.jpg',
            'Loose Local Photo': 'images/loose.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.short_card_photo_url, '')
        self.assertEqual(model.short_card_local_photo_path, '')
        self.assertEqual(model.exclusive_store, 'Walmart Exclusive')

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

    def test_import_can_read_nested_set_path_structure(self):
        payload = [{
            'Toy': 'HWFF01',
            'Number': '001',
            'Model Name': 'Nissan Skyline GT-R',
            'Series': "Fast & Furious: Brian O'Conner Series",
            'Series Number': '1/5',
            'Photo': 'https://example.com/skyline.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'hot-wheels' / 'semi-premium' / '2025' / 'fast-furious-brian-oconnor-series.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.brand, 'Hot Wheels')
        self.assertEqual(model.category, 'Semi Premium')
        self.assertEqual(model.year, 2025)

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
        self.assertEqual(model.series, 'HW Dream Garage')
        self.assertEqual(model.exclusive_store, 'Target Exclusive')

    def test_import_extracts_exclusive_store_and_special_tag(self):
        payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Chevy Bel AirSuper Treasure Hunt',
            'Series Number': '1/5',
            'Photo': 'https://example.com/car.jpg',
            'Local Photo': 'images/car.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.series, 'Chevy Bel Air')
        self.assertEqual(model.special_tag, 'Super Treasure Hunt')
        self.assertEqual(model.exclusive_store, '')

    def test_import_prefers_dataset_metadata_when_present(self):
        payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Chevy Bel AirWalmart Exclusive',
            'Exclusive Store': 'Kroger Exclusive',
            'Special Tag': 'ZAMAC',
            'Series Number': '1/5',
            'Photo': 'https://example.com/car.jpg',
            'Local Photo': 'images/car.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.series, 'Chevy Bel Air')
        self.assertEqual(model.exclusive_store, 'Kroger Exclusive')
        self.assertEqual(model.special_tag, 'ZAMAC')

    def test_import_does_not_store_new_in_mainline_as_special_tag(self):
        payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Compact KingsNew in Mainline',
            'Series Number': '1/5',
            'Photo': 'https://example.com/car.jpg',
            'Local Photo': 'images/car.jpg',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.series, 'Compact Kings')
        self.assertEqual(model.special_tag, '')


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

    def test_semi_premium_model_hides_short_card_variant(self):
        self.model_obj.category = 'Semi Premium'
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['category', 'short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['long_card', 'loose'])
        self.assertEqual(self.model_obj.short_card_image_src, '')

    def test_xl_model_hides_short_card_variant(self):
        self.model_obj.category = 'XL'
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['category', 'short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['long_card', 'loose'])
        self.assertEqual(self.model_obj.short_card_image_src, '')

    def test_premium_model_hides_short_card_variant(self):
        self.model_obj.category = 'Premium'
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['category', 'short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['long_card', 'loose'])
        self.assertEqual(self.model_obj.short_card_image_src, '')

    def test_rlc_model_hides_short_card_variant(self):
        self.model_obj.category = 'RLC'
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['category', 'short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['long_card', 'loose'])
        self.assertEqual(self.model_obj.short_card_image_src, '')

    def test_exclusive_model_hides_short_card_variant(self):
        self.model_obj.exclusive_store = 'Walmart Exclusive'
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['exclusive_store', 'short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['long_card', 'loose'])
        self.assertEqual(self.model_obj.short_card_image_src, '')

    def test_catalog_search(self):
        response = self.client.get(reverse('catalog:model-list'), {'q': 'Firebird'})
        self.assertContains(response, '1970 Pontiac Firebird')

    def test_catalog_search_can_parse_year_shortcut(self):
        HotWheelsModel.objects.create(
            app_id='def456',
            brand='Hot Wheels',
            toy='HCT06',
            number='002',
            model_name='Honda Civic Custom',
            year=2023,
            category='Mainline',
            series='HW J-Imports',
            series_number='2/5',
            photo_url='https://example.com/civic.jpg',
        )
        self.model_obj.model_name = 'Honda Civic Custom'
        self.model_obj.save(update_fields=['model_name'])

        response = self.client.get(reverse('catalog:model-list'), {'q': 'honda civic custom y:2022'})

        self.assertContains(response, 'Honda Civic Custom')
        self.assertNotContains(response, 'value="2023" selected')
        self.assertContains(response, 'value="honda civic custom y:2022"', html=False)

    def test_catalog_search_can_parse_quoted_shortcuts(self):
        self.model_obj.exclusive_store = 'Walmart Exclusive'
        self.model_obj.category = 'Semi Premium'
        self.model_obj.special_tag = 'Super Treasure Hunt'
        self.model_obj.save(update_fields=['exclusive_store', 'category', 'special_tag'])
        HotWheelsModel.objects.create(
            app_id='def457',
            brand='Hot Wheels',
            toy='HCT07',
            number='003',
            model_name='Other Car',
            year=2022,
            category='Mainline',
            series='Muscle Mania',
            series_number='3/5',
            photo_url='https://example.com/other.jpg',
        )

        response = self.client.get(
            reverse('catalog:model-list'),
            {'q': 'firebird c:"Semi Premium" x:"Walmart Exclusive" t:"Super Treasure Hunt"'},
        )

        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertNotContains(response, 'Other Car')
        self.assertContains(response, '<option value="Semi Premium" selected>', html=False)
        self.assertContains(response, '<option value="Walmart Exclusive" selected>', html=False)
        self.assertContains(response, '<option value="Super Treasure Hunt" selected>', html=False)

    def test_catalog_shows_summary_stats(self):
        HotWheelsModel.objects.create(
            app_id='def456',
            brand='Matchbox',
            toy='MBX01',
            number='002',
            model_name='Custom Mustang',
            year=2023,
            category='Collectors',
            series='MBX Road Trip',
            series_number='2/5',
            photo_url='https://example.com/mustang.jpg',
        )

        response = self.client.get(reverse('catalog:model-list'), {'brand': 'Hot Wheels'})

        self.assertContains(response, 'Modele w bazie')
        self.assertContains(response, 'Wyniki po filtrach')
        self.assertContains(response, 'Marki')
        self.assertContains(response, 'Roczniki')
        self.assertContains(response, 'Kategorie')
        self.assertContains(response, '<strong class="stat-value">2</strong>', html=True)
        self.assertContains(response, '<strong class="stat-value">1</strong>', html=True)

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

    def test_catalog_can_filter_by_exclusive_store_and_special_tag(self):
        self.model_obj.exclusive_store = 'Walmart Exclusive'
        self.model_obj.save(update_fields=['exclusive_store'])
        second_model = HotWheelsModel.objects.create(
            app_id='def456',
            brand='Hot Wheels',
            toy='HCT06',
            number='002',
            model_name='Custom Mustang',
            year=2023,
            category='Mainline',
            series='Muscle Mania',
            special_tag='Super Treasure Hunt',
            series_number='2/5',
            photo_url='https://example.com/mustang.jpg',
        )

        response = self.client.get(reverse('catalog:model-list'), {'exclusive_store': 'Walmart Exclusive'})

        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertNotContains(response, 'Custom Mustang')

        response = self.client.get(reverse('catalog:model-list'), {'special_tag': 'Super Treasure Hunt'})

        self.assertContains(response, 'Custom Mustang')
        self.assertNotContains(response, '1970 Pontiac Firebird')

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

    def test_semi_premium_model_detail_hides_short_card(self):
        self.model_obj.category = 'Semi Premium'
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['category', 'short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        response = self.client.get(reverse('catalog:model-detail', args=[self.model_obj.pk]))

        self.assertNotContains(response, 'Krótka karta')
        self.assertContains(response, 'Długa karta')
        self.assertContains(response, 'Luzak')

    def test_healthcheck(self):
        response = self.client.get(reverse('healthcheck'))
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'status': 'ok'})


class CatalogDedupeCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='owner@example.com', password='ComplexPass123')
        self.collection = Collection.objects.create(owner=self.user, name='Moja', kind=Collection.KIND_OWNED)

    def test_dedupe_catalog_models_removes_duplicate_models(self):
        canonical = HotWheelsModel.objects.create(
            app_id='dup-1',
            brand='Hot Wheels',
            category='Mainline',
            year=2023,
            toy='ABC',
            number='001',
            model_name='Test Car',
            series='Series A',
            series_number='1/5',
            photo_url='https://example.com/car.jpg',
            local_photo_path='images/car.jpg',
        )
        HotWheelsModel.objects.create(
            app_id='dup-2',
            brand='Hot Wheels',
            category='Mainline',
            year=2023,
            toy='ABC',
            number='001',
            model_name='Test Car',
            series='Series A',
            series_number='1/5',
            photo_url='',
            local_photo_path='',
        )

        call_command('dedupe_catalog_models', brand='Hot Wheels', category='Mainline', year=2023)

        self.assertEqual(HotWheelsModel.objects.filter(year=2023).count(), 1)
        self.assertTrue(HotWheelsModel.objects.filter(pk=canonical.pk).exists())

    def test_dedupe_catalog_models_merges_collection_items(self):
        canonical = HotWheelsModel.objects.create(
            app_id='dup-1',
            brand='Hot Wheels',
            category='Mainline',
            year=2023,
            toy='ABC',
            number='001',
            model_name='Test Car',
            series='Series A',
            series_number='1/5',
            photo_url='https://example.com/car.jpg',
            local_photo_path='images/car.jpg',
        )
        duplicate = HotWheelsModel.objects.create(
            app_id='dup-2',
            brand='Hot Wheels',
            category='Mainline',
            year=2023,
            toy='ABC',
            number='001',
            model_name='Test Car',
            series='Series A',
            series_number='1/5',
            photo_url='',
            local_photo_path='',
        )
        CollectionItem.objects.create(
            collection=self.collection,
            model=canonical,
            quantity=1,
            condition='good',
            packaging_state='short_card',
            notes='canon',
        )
        CollectionItem.objects.create(
            collection=self.collection,
            model=duplicate,
            quantity=2,
            condition='good',
            packaging_state='short_card',
            notes='dupe',
            is_favorite=True,
        )

        call_command('dedupe_catalog_models', brand='Hot Wheels', category='Mainline', year=2023)

        item = CollectionItem.objects.get(collection=self.collection, model=canonical, condition='good', packaging_state='short_card')
        self.assertEqual(item.quantity, 3)
        self.assertTrue(item.is_favorite)
        self.assertIn('canon', item.notes)
        self.assertIn('dupe', item.notes)
        self.assertFalse(CollectionItem.objects.filter(model=duplicate).exists())
