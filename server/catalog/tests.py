import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from collections_app.models import Collection, CollectionItem, WantedItem

from .management.commands.import_models import Command
from .models import HotWheelsModel


class ImportModelsCommandTests(TestCase):
    def test_clean_model_name_removes_color_variant_suffix(self):
        self.assertEqual(Command.clean_model_name('Honda Civic (2nd color)'), 'Honda Civic')
        self.assertEqual(Command.clean_model_name('Toyota Supra (3rd color)'), 'Toyota Supra')
        self.assertEqual(Command.clean_model_name('Honda Civic (2nd color - zamac)'), 'Honda Civic')
        self.assertEqual(Command.clean_model_name('Toyota Supra (3rd color - zamac)'), 'Toyota Supra')
        self.assertEqual(Command.clean_model_name('Mazda RX-7'), 'Mazda RX-7')

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

    def test_import_backfills_only_short_card_photo_from_default_photo(self):
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
        self.assertEqual(model.long_card_photo_url, '')
        self.assertEqual(model.loose_photo_url, '')
        self.assertEqual(model.short_card_local_photo_path, 'images/car.jpg')
        self.assertEqual(model.long_card_local_photo_path, '')
        self.assertEqual(model.loose_local_photo_path, '')

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

    def test_import_removes_color_variant_suffix_from_model_name(self):
        payload = [{
            'Toy': 'HW01',
            'Number': '001',
            'Model Name': 'Honda Civic (2nd color - zamac)',
            'Series': 'Series A',
            'Series Number': '1/5',
        }]

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / 'models.json'
            path.write_text(json.dumps(payload))
            call_command('import_models', path=str(path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.model_name, 'Honda Civic')

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

    def test_import_normalizes_and_merges_case_codes(self):
        initial_payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A',
            'Series Number': '1/5',
            'Case': 'A case',
        }]
        second_payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A',
            'Series Number': '1/5',
            'Case': 'B',
        }]
        third_payload = [{
            'Toy': 'ABC',
            'Number': '001',
            'Model Name': 'Test Car',
            'Series': 'Series A',
            'Series Number': '1/5',
        }]

        with TemporaryDirectory() as tmpdir:
            first_path = Path(tmpdir) / 'first.json'
            second_path = Path(tmpdir) / 'second.json'
            third_path = Path(tmpdir) / 'third.json'
            first_path.write_text(json.dumps(initial_payload))
            second_path.write_text(json.dumps(second_payload))
            third_path.write_text(json.dumps(third_payload))
            call_command('import_models', path=str(first_path))
            call_command('import_models', path=str(second_path))
            call_command('import_models', path=str(third_path))

        model = HotWheelsModel.objects.get()
        self.assertEqual(model.case_codes, 'A,B')


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
        self.assertNotContains(response, 'data-image-label=')

    def test_catalog_model_exposes_packaging_variants(self):
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = ''
        self.model_obj.save(update_fields=['short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['short_card', 'long_card'])
        self.assertEqual(self.model_obj.catalog_primary_image_src, 'https://example.com/long.jpg')
        self.assertEqual(self.model_obj.catalog_primary_thumb_src, 'https://example.com/long.jpg')
        self.assertEqual(self.model_obj.catalog_primary_preview_src, 'https://example.com/long.jpg')

    def test_catalog_model_treats_identical_packaging_images_as_one_unassigned_photo(self):
        self.model_obj.short_card_photo_url = 'https://example.com/car.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/car.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/car.jpg'
        self.model_obj.save(update_fields=['short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['default'])
        self.assertTrue(self.model_obj.has_unassigned_image)
        self.assertEqual(self.model_obj.missing_packaging_image_states, ['short_card', 'long_card', 'loose'])

    def test_catalog_model_uses_generic_image_when_packaging_duplicates_match_it(self):
        self.model_obj.photo_url = 'https://example.com/car.jpg'
        self.model_obj.short_card_photo_url = 'https://example.com/car.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/car.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/car.jpg'
        self.model_obj.save(
            update_fields=['photo_url', 'short_card_photo_url', 'long_card_photo_url', 'loose_photo_url']
        )

        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['default'])
        self.assertEqual(self.model_obj.unassigned_image_reference['url'], 'https://example.com/car.jpg')
        self.assertEqual(self.model_obj.missing_packaging_image_states, ['short_card', 'long_card', 'loose'])

    def test_catalog_model_treats_generic_image_as_unassigned(self):
        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['default'])
        self.assertTrue(self.model_obj.has_unassigned_image)
        self.assertEqual(self.model_obj.missing_packaging_image_states, ['short_card', 'long_card', 'loose'])

    def test_build_image_variant_relative_path(self):
        self.assertEqual(
            HotWheelsModel.build_image_variant_relative_path('images/hot-wheels/mainline/car.jpg', 'thumb'),
            'images/hot-wheels/mainline/car--thumb.webp',
        )
        self.assertEqual(
            HotWheelsModel.build_image_variant_relative_path('images/hot-wheels/mainline/car.png', 'preview'),
            'images/hot-wheels/mainline/car--preview.webp',
        )

    def test_semi_premium_model_hides_short_card_variant(self):
        self.model_obj.category = 'Semi Premium'
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['category', 'short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        variants = self.model_obj.catalog_image_variants

        self.assertEqual([variant['key'] for variant in variants], ['long_card', 'loose'])
        self.assertEqual(self.model_obj.short_card_image_src, '')

    def test_semi_premium_model_with_complete_packaging_has_no_unassigned_image(self):
        self.model_obj.category = 'Semi Premium'
        self.model_obj.photo_url = 'https://example.com/generic.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['category', 'photo_url', 'long_card_photo_url', 'loose_photo_url'])

        self.assertFalse(self.model_obj.has_unassigned_image)
        self.assertEqual(self.model_obj.missing_packaging_image_states, [])

    def test_premium_model_with_complete_packaging_has_no_unassigned_image(self):
        self.model_obj.category = 'Premium'
        self.model_obj.photo_url = 'https://example.com/generic.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['category', 'photo_url', 'long_card_photo_url', 'loose_photo_url'])

        self.assertFalse(self.model_obj.has_unassigned_image)
        self.assertEqual(self.model_obj.missing_packaging_image_states, [])

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

    def test_catalog_search_suggestions_returns_matching_models(self):
        HotWheelsModel.objects.create(
            app_id='def455',
            brand='Hot Wheels',
            toy='HCT04',
            number='000',
            model_name='Toyota Supra',
            year=2024,
            category='Mainline',
            series='HW Turbo',
            series_number='1/5',
            photo_url='https://example.com/supra.jpg',
        )

        response = self.client.get(reverse('catalog:model-search-suggestions'), {'q': 'toyota'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()['suggestions'][0]['value'],
            'Toyota Supra',
        )

    def test_catalog_can_render_table_view(self):
        response = self.client.get(reverse('catalog:model-list'), {'view': 'table'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<table class="catalog-table">', html=False)
        self.assertEqual(response.context['selected_view'], 'table')

    def test_catalog_table_view_can_change_page_size(self):
        response = self.client.get(
            reverse('catalog:model-list'),
            {'view': 'table', 'per_page': '50'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_view'], 'table')
        self.assertEqual(response.context['selected_per_page'], '50')
        self.assertEqual(response.context['paginator'].per_page, 50)
        self.assertContains(response, 'per_page=50', html=False)

    def test_catalog_table_view_can_sort_by_column_descending(self):
        HotWheelsModel.objects.create(
            app_id='def458',
            brand='Hot Wheels',
            toy='HCT08',
            number='099',
            model_name='Aston Martin Vantage',
            year=2024,
            category='Mainline',
            series='HW Exotics',
            series_number='4/5',
            photo_url='https://example.com/aston.jpg',
        )

        response = self.client.get(
            reverse('catalog:model-list'),
            {'view': 'table', 'sort': '-name'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_sort'], '-name')
        self.assertEqual(
            [item.model_name for item in response.context['models']],
            ['Aston Martin Vantage', '1970 Pontiac Firebird'],
        )

    def test_catalog_marks_models_already_owned(self):
        user = User.objects.create_user(email='collector@example.com', password='ComplexPass123')
        collection = Collection.objects.create(owner=user, name='Moja kolekcja', kind=Collection.KIND_OWNED)
        CollectionItem.objects.create(collection=collection, model=self.model_obj, quantity=2)
        HotWheelsModel.objects.create(
            app_id='def459',
            brand='Hot Wheels',
            toy='HCT09',
            number='004',
            model_name='Unowned Car',
            year=2024,
            category='Mainline',
            series='HW Dream Garage',
            series_number='4/5',
            photo_url='https://example.com/case-b.jpg',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('catalog:model-list'), {'view': 'table'})

        self.assertContains(response, 'Masz w kolekcji')
        self.assertContains(response, '2 szt. | 1 wpis')
        self.assertContains(response, 'Unowned Car')
        self.assertContains(response, 'name="model_ids"', html=False)

    def test_catalog_can_filter_only_unowned_models(self):
        user = User.objects.create_user(email='collector2@example.com', password='ComplexPass123')
        collection = Collection.objects.create(owner=user, name='Moja kolekcja', kind=Collection.KIND_OWNED)
        CollectionItem.objects.create(collection=collection, model=self.model_obj, quantity=1)
        unowned_model = HotWheelsModel.objects.create(
            app_id='def460',
            brand='Hot Wheels',
            toy='HCT10',
            number='005',
            model_name='Unowned Honda',
            year=2024,
            category='Mainline',
            series='HW J-Imports',
            series_number='5/5',
            photo_url='https://example.com/honda.jpg',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('catalog:model-list'), {'view': 'table', 'only_unowned': '1'})

        self.assertEqual(response.context['selected_only_unowned'], '1')
        self.assertContains(response, 'Unowned Honda')
        self.assertNotContains(response, '1970 Pontiac Firebird')
        self.assertContains(response, 'Tylko nieposiadane')

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

    def test_catalog_search_shortcuts_support_partial_exclusive_match(self):
        self.model_obj.exclusive_store = 'Walmart Exclusive'
        self.model_obj.save(update_fields=['exclusive_store'])
        HotWheelsModel.objects.create(
            app_id='def457a',
            brand='Hot Wheels',
            toy='HCT07A',
            number='003',
            model_name='Target Car',
            year=2022,
            category='Mainline',
            series='Muscle Mania',
            exclusive_store='Target Exclusive',
            series_number='3/5',
            photo_url='https://example.com/target.jpg',
        )

        response = self.client.get(reverse('catalog:model-list'), {'q': 'x:Walmart'})

        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertNotContains(response, 'Target Car')

    def test_catalog_search_shortcuts_support_partial_special_tag_match(self):
        self.model_obj.special_tag = 'Treasure Hunt'
        self.model_obj.save(update_fields=['special_tag'])
        HotWheelsModel.objects.create(
            app_id='def457b',
            brand='Hot Wheels',
            toy='HCT07B',
            number='004',
            model_name='Super Treasure Car',
            year=2022,
            category='Mainline',
            series='HW Dream Garage',
            special_tag='Super Treasure Hunt',
            series_number='4/5',
            photo_url='https://example.com/super-treasure.jpg',
        )
        HotWheelsModel.objects.create(
            app_id='def457c',
            brand='Hot Wheels',
            toy='HCT07C',
            number='005',
            model_name='Regular Car',
            year=2022,
            category='Mainline',
            series='HW Dream Garage',
            series_number='5/5',
            photo_url='https://example.com/regular.jpg',
        )

        response = self.client.get(reverse('catalog:model-list'), {'q': 't:Treasure'})

        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertContains(response, 'Super Treasure Car')
        self.assertNotContains(response, 'Regular Car')

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

        self.assertContains(response, 'Wyniki: 1')
        self.assertContains(response, 'Hot Wheels')
        self.assertNotContains(response, 'Custom Mustang')
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

    def test_catalog_can_filter_by_case_code(self):
        self.model_obj.case_codes = 'A,C'
        self.model_obj.save(update_fields=['case_codes'])
        HotWheelsModel.objects.create(
            app_id='def458',
            brand='Hot Wheels',
            toy='HCT08',
            number='003',
            model_name='Other Car',
            year=2024,
            category='Mainline',
            series='Muscle Mania',
            case_codes='B',
            series_number='3/5',
            photo_url='https://example.com/other.jpg',
        )

        response = self.client.get(reverse('catalog:model-list'), {'case_code': 'A'})

        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertNotContains(response, 'Other Car')
        self.assertContains(response, '<option value="A" selected>', html=False)

    def test_catalog_filter_options_follow_other_selected_filters(self):
        self.model_obj.case_codes = 'A,C'
        self.model_obj.save(update_fields=['case_codes'])
        HotWheelsModel.objects.create(
            app_id='def460',
            brand='Hot Wheels',
            toy='HCT10',
            number='005',
            model_name='Premium Car',
            year=2024,
            category='Premium',
            series='Car Culture',
            case_codes='ZAMAC',
            series_number='1/5',
            photo_url='https://example.com/premium.jpg',
        )

        response = self.client.get(reverse('catalog:model-list'), {'category': 'Premium'})

        self.assertContains(response, '<option value="Premium" selected>', html=False)
        self.assertContains(response, 'data-filter-field="case-mix"', html=False)
        self.assertContains(response, 'id="case_code" name="case_code" disabled', html=False)
        self.assertNotContains(response, '<option value="ZAMAC">', html=False)
        self.assertNotContains(response, '<option value="A">', html=False)

    def test_catalog_ignores_case_code_for_premium_category(self):
        self.model_obj.category = 'Premium'
        self.model_obj.case_codes = 'A'
        self.model_obj.save(update_fields=['category', 'case_codes'])
        HotWheelsModel.objects.create(
            app_id='def461',
            brand='Hot Wheels',
            toy='HCT11',
            number='006',
            model_name='Second Premium Car',
            year=2024,
            category='Premium',
            series='Car Culture',
            case_codes='B',
            series_number='2/5',
            photo_url='https://example.com/premium-second.jpg',
        )

        response = self.client.get(reverse('catalog:model-list'), {'category': 'Premium', 'case_code': 'A'})

        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertContains(response, 'Second Premium Car')
        self.assertNotContains(response, '<option value="A" selected>', html=False)

    def test_catalog_search_can_parse_case_shortcut(self):
        self.model_obj.case_codes = 'A,C'
        self.model_obj.save(update_fields=['case_codes'])
        HotWheelsModel.objects.create(
            app_id='def459',
            brand='Hot Wheels',
            toy='HCT09',
            number='004',
            model_name='Case B Car',
            year=2024,
            category='Mainline',
            series='HW Dream Garage',
            case_codes='B',
            series_number='4/5',
            photo_url='https://example.com/case-b.jpg',
        )

        response = self.client.get(reverse('catalog:model-list'), {'q': 'firebird case:a'})

        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertNotContains(response, 'Case B Car')

    def test_case_mix_list_view(self):
        self.model_obj.year = 2026
        self.model_obj.case_codes = 'A,B'
        self.model_obj.special_tag = 'Treasure Hunt'
        self.model_obj.save(update_fields=['year', 'case_codes', 'special_tag'])
        HotWheelsModel.objects.create(
            app_id='case-list-2',
            brand='Hot Wheels',
            toy='HCT10',
            number='002',
            model_name='Second Case Car',
            year=2026,
            category='Mainline',
            series='HW Dream Garage',
            case_codes='C',
            special_tag='Super Treasure Hunt',
            series_number='2/5',
            photo_url='https://example.com/second.jpg',
        )

        response = self.client.get(reverse('catalog:case-mix-list'))

        self.assertContains(response, 'Lista case’ów według roczników')
        self.assertContains(response, '2026')
        self.assertContains(response, 'Case A')
        self.assertContains(response, 'Case B')
        self.assertContains(response, 'Case C')
        self.assertContains(response, reverse('catalog:case-mix-detail', args=[2026, 'a']))
        self.assertContains(response, reverse('catalog:case-mix-detail', args=[2026, 'b']))
        self.assertContains(response, reverse('catalog:case-mix-detail', args=[2026, 'c']))

    def test_case_mix_detail_view(self):
        self.model_obj.year = 2026
        self.model_obj.case_codes = 'A'
        self.model_obj.special_tag = 'Treasure Hunt'
        self.model_obj.save(update_fields=['year', 'case_codes', 'special_tag'])
        HotWheelsModel.objects.create(
            app_id='case-detail-2',
            brand='Hot Wheels',
            toy='HCT12',
            number='002',
            model_name='Second Case Car',
            year=2026,
            category='Mainline',
            series='HW Dream Garage',
            case_codes='A',
            special_tag='Super Treasure Hunt',
            series_number='2/5',
            photo_url='https://example.com/second.jpg',
        )

        response = self.client.get(reverse('catalog:case-mix-detail', args=[2026, 'a']))

        self.assertContains(response, 'Mainline 2026 Case A')
        self.assertContains(response, 'Modele w case A')
        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertContains(response, 'Second Case Car')
        self.assertContains(response, 'Treasure Hunt')
        self.assertContains(response, 'Super Treasure Hunt')
        self.assertContains(response, 'Otwórz ten case w katalogu')
        self.assertContains(response, reverse('catalog:case-mix-list'))

    def test_case_mix_views_can_render_from_metadata_without_models(self):
        response = self.client.get(reverse('catalog:case-mix-list'))
        self.assertContains(response, '2025')
        self.assertContains(response, reverse('catalog:case-mix-detail', args=[2025, 'q']))

        detail_response = self.client.get(reverse('catalog:case-mix-detail', args=[2025, 'q']))
        self.assertContains(detail_response, 'Mainline 2025 Case Q')

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

    def test_catalog_admin_dashboard_shows_image_quality_stats(self):
        admin = User.objects.create_user(
            email='quality-admin@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.client.force_login(admin)
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.photo_url = ''
        self.model_obj.save(update_fields=['short_card_photo_url', 'long_card_photo_url', 'loose_photo_url', 'photo_url'])
        HotWheelsModel.objects.create(
            app_id='quality-premium',
            brand='Hot Wheels',
            toy='JBL17',
            number='1/5',
            model_name='Premium Review Car',
            year=2025,
            category='Premium',
            series='Hot Wheels Boulevard - Mix 1',
            photo_url='https://example.com/premium-generic.jpg',
            long_card_photo_url='https://example.com/premium-long.jpg',
        )

        response = self.client.get(reverse('catalog:admin-dashboard'))

        self.assertContains(response, 'Panel admina')
        self.assertContains(response, 'Komplet zdjęć')
        self.assertContains(response, 'Brakujące warianty zdjęć')
        self.assertContains(response, 'Nieprzypisane zdjęcia')
        self.assertContains(response, 'Przypisane zdjęcia')
        self.assertContains(response, 'Modele według kategorii')
        self.assertContains(response, 'Mainline')
        self.assertContains(response, 'Premium')
        self.assertNotContains(response, 'Zakres bazy')

    def test_catalog_admin_dashboard_requires_staff(self):
        user = User.objects.create_user(email='plain@example.com', password='ComplexPass123')
        self.client.force_login(user)

        response = self.client.get(reverse('catalog:admin-dashboard'))

        self.assertEqual(response.status_code, 403)

    def test_catalog_admin_dashboard_shows_image_workflow_counts(self):
        admin = User.objects.create_user(
            email='staff@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.save(update_fields=['short_card_photo_url'])
        HotWheelsModel.objects.create(
            app_id='admin-complete',
            brand='Hot Wheels',
            toy='HCT20',
            number='020',
            model_name='Complete Admin Car',
            year=2024,
            category='Premium',
            photo_url='',
            long_card_photo_url='https://example.com/long.jpg',
            loose_photo_url='https://example.com/loose.jpg',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('catalog:admin-dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Panel admina')
        self.assertContains(response, 'Brakujące warianty')
        self.assertContains(response, 'Nieprzypisane zdjęcia')
        self.assertContains(response, 'Komplet zdjęć')
        self.assertContains(response, 'Verified')
        self.assertContains(response, 'Modele według kategorii')
        self.assertContains(response, reverse('catalog:missing-packaging-images'))
        self.assertContains(response, reverse('catalog:unassigned-images'))
        self.assertContains(response, reverse('catalog:assigned-images'))
        self.assertContains(response, reverse('catalog:complete-images'))

    def test_model_detail(self):
        self.model_obj.case_codes = 'A,Q'
        self.model_obj.save(update_fields=['case_codes'])
        response = self.client.get(reverse('catalog:model-detail', args=[self.model_obj.pk]))
        self.assertContains(response, 'HCT05')
        self.assertContains(response, 'Hot Wheels')
        self.assertContains(response, '2022')
        self.assertContains(response, 'Mainline')
        self.assertContains(response, "Case'y modelu")
        self.assertContains(response, reverse('catalog:case-mix-detail', args=[2022, 'a']))
        self.assertContains(response, reverse('catalog:case-mix-detail', args=[2022, 'q']))

    def test_model_detail_shows_similar_models(self):
        same_series_same_year = HotWheelsModel.objects.create(
            app_id='sim-1',
            brand='Hot Wheels',
            toy='HCT06',
            number='002',
            model_name='Custom Mustang',
            year=2022,
            category='Mainline',
            series='HW Dream Garage',
            photo_url='https://example.com/mustang.jpg',
        )
        same_category_same_year = HotWheelsModel.objects.create(
            app_id='sim-2',
            brand='Hot Wheels',
            toy='HCT07',
            number='003',
            model_name='Mazda RX-7',
            year=2022,
            category='Mainline',
            series='HW Drift',
            photo_url='https://example.com/rx7.jpg',
        )

        response = self.client.get(reverse('catalog:model-detail', args=[self.model_obj.pk]))

        self.assertContains(response, 'Podobne modele')
        self.assertContains(response, same_series_same_year.model_name)
        self.assertContains(response, same_category_same_year.model_name)
        self.assertContains(response, reverse('catalog:model-detail', args=[same_series_same_year.pk]))

    def test_authenticated_model_detail_shows_owned_and_wanted_state(self):
        user = User.objects.create_user(email='collector@example.com', password='ComplexPass123')
        collection = Collection.objects.create(owner=user, name='Główna', kind=Collection.KIND_OWNED)
        owned_item = CollectionItem.objects.create(
            collection=collection,
            model=self.model_obj,
            quantity=2,
            packaging_state='loose',
            condition='good',
        )
        wanted_item = WantedItem.objects.create(
            owner=user,
            model=self.model_obj,
            packaging_state='long_card',
            condition_min='mint',
            is_active=True,
        )

        self.client.force_login(user)
        response = self.client.get(reverse('catalog:model-detail', args=[self.model_obj.pk]))

        self.assertContains(response, 'Twoja kolekcja')
        self.assertContains(response, 'Główna')
        self.assertContains(response, '2 sztuk')
        self.assertContains(response, 'Luzak')
        self.assertContains(response, reverse('collections:item-update', args=[owned_item.pk]))
        self.assertContains(response, 'Twoje szukane')
        self.assertContains(response, 'Aktywne')
        self.assertContains(response, 'Długa karta')
        self.assertContains(response, reverse('collections:wanted-update', args=[wanted_item.pk]))
        self.assertContains(response, f'{reverse("catalog:model-list")}?year=2022')
        self.assertContains(response, f'{reverse("catalog:model-list")}?category=Mainline')
        self.assertContains(response, f'{reverse("catalog:model-list")}?series=HW+Dream+Garage&amp;year=2022')

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

    def test_model_detail_hides_duplicate_packaging_panels(self):
        response = self.client.get(reverse('catalog:model-detail', args=[self.model_obj.pk]))

        self.assertEqual([panel['key'] for panel in response.context['model_obj'].packaging_image_panels], [])
        self.assertContains(response, 'Zdjęcie modelu')
        self.assertNotContains(response, 'Nieprzypisane zdjęcie')
        self.assertNotContains(response, 'Brakujące warianty zdjęć')

    def test_model_detail_shows_generic_and_assigned_images_together(self):
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.save(update_fields=['long_card_photo_url'])

        response = self.client.get(reverse('catalog:model-detail', args=[self.model_obj.pk]))

        self.assertContains(response, 'Zdjęcie modelu')
        self.assertContains(response, 'Długa karta')
        self.assertContains(response, 'https://example.com/car.jpg')
        self.assertContains(response, 'https://example.com/long.jpg')

    def test_staff_model_detail_shows_verified_controls_for_complete_images(self):
        admin = User.objects.create_user(
            email='staff-verify@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.photo_url = ''
        self.model_obj.save(update_fields=['short_card_photo_url', 'long_card_photo_url', 'loose_photo_url', 'photo_url'])
        self.client.force_login(admin)

        response = self.client.get(reverse('catalog:model-detail', args=[self.model_obj.pk]))

        self.assertContains(response, 'Oznacz jako verified')
        self.assertContains(response, 'Do weryfikacji')

    def test_missing_packaging_images_view_lists_models_with_missing_slots(self):
        complete_model = HotWheelsModel.objects.create(
            app_id='def777',
            brand='Hot Wheels',
            toy='HCT99',
            number='099',
            model_name='Complete Car',
            year=2024,
            category='Mainline',
            series='HW Metro',
            series_number='1/5',
            photo_url='https://example.com/complete-short.jpg',
            short_card_photo_url='https://example.com/complete-short.jpg',
            long_card_photo_url='https://example.com/complete-long.jpg',
            loose_photo_url='https://example.com/complete-loose.jpg',
        )
        self.model_obj.short_card_photo_url = 'https://example.com/car.jpg'
        self.model_obj.long_card_photo_url = ''
        self.model_obj.loose_photo_url = ''
        self.model_obj.save(update_fields=['short_card_photo_url', 'long_card_photo_url', 'loose_photo_url'])

        response = self.client.get(reverse('catalog:missing-packaging-images'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertContains(response, 'Brak długiej karty', html=False)
        self.assertContains(response, 'Brak luzaka', html=False)
        self.assertNotContains(response, complete_model.model_name)

    def test_missing_packaging_images_view_supports_year_series_and_sort_filters(self):
        HotWheelsModel.objects.create(
            app_id='missing-older',
            brand='Hot Wheels',
            toy='HCT11',
            number='011',
            model_name='Alpha Missing',
            year=2021,
            category='Mainline',
            series='HW Drift',
            photo_url='https://example.com/alpha.jpg',
            short_card_photo_url='https://example.com/alpha.jpg',
        )
        HotWheelsModel.objects.create(
            app_id='missing-same-series',
            brand='Hot Wheels',
            toy='HCT12',
            number='012',
            model_name='Beta Missing',
            year=2021,
            category='Mainline',
            series='HW Dream Garage',
            photo_url='https://example.com/beta.jpg',
            short_card_photo_url='https://example.com/beta.jpg',
        )

        response = self.client.get(reverse('catalog:missing-packaging-images'), {
            'year': '2021',
            'series': 'HW Dream Garage',
            'sort': 'name',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Beta Missing')
        self.assertNotContains(response, 'Alpha Missing')
        self.assertContains(response, 'value="2021" selected')
        self.assertContains(response, 'value="HW Dream Garage" selected')

    def test_unassigned_images_view_lists_models_with_generic_images(self):
        admin = User.objects.create_user(
            email='admin2@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('catalog:unassigned-images'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertContains(response, 'Nieprzypisane zdjęcia')

    def test_unassigned_images_view_passes_workflow_navigation_to_detail(self):
        admin = User.objects.create_user(
            email='admin-nav@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        previous_model = HotWheelsModel.objects.create(
            app_id='nav-1',
            brand='Hot Wheels',
            toy='HCT01',
            number='001',
            model_name='A Model',
            year=2022,
            category='Mainline',
            series='HW Dream Garage',
            photo_url='https://example.com/a.jpg',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('catalog:model-detail', args=[self.model_obj.pk]), {
            'workflow': 'unassigned',
            'category': 'Mainline',
            'sort': 'name',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nieprzypisane zdjęcia')
        self.assertContains(
            response,
            f'{reverse("catalog:model-detail", args=[previous_model.pk])}?workflow=unassigned&amp;category=Mainline&amp;sort=name',
        )
        self.assertContains(
            response,
            f'{reverse("catalog:unassigned-images")}?category=Mainline&amp;sort=name',
        )

    def test_unassigned_images_view_excludes_premium_models_with_complete_packaging(self):
        admin = User.objects.create_user(
            email='admin6@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.category = 'Premium'
        self.model_obj.photo_url = 'https://example.com/generic.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.save(update_fields=['category', 'photo_url', 'long_card_photo_url', 'loose_photo_url'])
        self.client.force_login(admin)

        response = self.client.get(reverse('catalog:unassigned-images'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '1970 Pontiac Firebird')

    def test_non_staff_cannot_open_unassigned_images_view(self):
        user = User.objects.create_user(
            email='user@example.com',
            password='ComplexPass123',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('catalog:unassigned-images'))

        self.assertEqual(response.status_code, 403)

    def test_staff_can_assign_generic_image_to_packaging_state(self):
        admin = User.objects.create_user(
            email='admin@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse('catalog:assign-generic-image', args=[self.model_obj.pk, 'long_card']),
            {'next': reverse('catalog:unassigned-images')},
        )

        self.assertRedirects(response, reverse('catalog:unassigned-images'))
        self.model_obj.refresh_from_db()
        self.assertEqual(self.model_obj.photo_url, '')
        self.assertEqual(self.model_obj.local_photo_path, '')
        self.assertEqual(self.model_obj.long_card_photo_url, 'https://example.com/car.jpg')
        self.assertEqual([panel['key'] for panel in self.model_obj.packaging_image_panels], ['long_card'])

    def test_staff_can_reassign_packaging_image_to_other_variant(self):
        admin = User.objects.create_user(
            email='admin3@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.save(update_fields=['long_card_photo_url'])
        self.client.force_login(admin)

        response = self.client.post(
            reverse('catalog:reassign-packaging-image', args=[self.model_obj.pk, 'long_card', 'loose']),
            {'next': reverse('catalog:model-detail', args=[self.model_obj.pk])},
        )

        self.assertRedirects(response, reverse('catalog:model-detail', args=[self.model_obj.pk]))
        self.model_obj.refresh_from_db()
        self.assertEqual(self.model_obj.long_card_photo_url, '')
        self.assertEqual(self.model_obj.loose_photo_url, 'https://example.com/long.jpg')

    def test_staff_can_move_packaging_image_back_to_unassigned(self):
        admin = User.objects.create_user(
            email='admin4@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.photo_url = ''
        self.model_obj.save(update_fields=['long_card_photo_url', 'photo_url'])
        self.client.force_login(admin)

        response = self.client.post(
            reverse('catalog:reassign-packaging-image', args=[self.model_obj.pk, 'long_card', 'unassigned']),
            {'next': reverse('catalog:model-detail', args=[self.model_obj.pk])},
        )

        self.assertRedirects(response, reverse('catalog:model-detail', args=[self.model_obj.pk]))
        self.model_obj.refresh_from_db()
        self.assertEqual(self.model_obj.long_card_photo_url, '')
        self.assertEqual(self.model_obj.photo_url, 'https://example.com/long.jpg')

    def test_staff_cannot_overwrite_existing_unassigned_image_when_moving_back(self):
        admin = User.objects.create_user(
            email='admin4b@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.photo_url = 'https://example.com/generic.jpg'
        self.model_obj.save(update_fields=['long_card_photo_url', 'photo_url'])
        self.client.force_login(admin)

        response = self.client.post(
            reverse('catalog:reassign-packaging-image', args=[self.model_obj.pk, 'long_card', 'unassigned']),
            {'next': reverse('catalog:model-detail', args=[self.model_obj.pk])},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.model_obj.refresh_from_db()
        self.assertEqual(self.model_obj.long_card_photo_url, 'https://example.com/long.jpg')
        self.assertEqual(self.model_obj.photo_url, 'https://example.com/generic.jpg')
        self.assertContains(response, 'Model ma już nieprzypisane zdjęcie.')

    def test_staff_can_open_assigned_images_view(self):
        admin = User.objects.create_user(
            email='admin5@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.save(update_fields=['long_card_photo_url'])
        self.client.force_login(admin)

        response = self.client.get(reverse('catalog:assigned-images'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Przypisane zdjęcia')
        self.assertContains(response, '1970 Pontiac Firebird')

    def test_staff_can_open_complete_images_view(self):
        admin = User.objects.create_user(
            email='admin-complete@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.photo_url = ''
        self.model_obj.save(update_fields=['short_card_photo_url', 'long_card_photo_url', 'loose_photo_url', 'photo_url'])
        self.client.force_login(admin)

        response = self.client.get(reverse('catalog:complete-images'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Komplet zdjęć')
        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertContains(response, 'Do weryfikacji')

    def test_complete_images_view_includes_complete_models_with_generic_photo_left_in_data(self):
        admin = User.objects.create_user(
            email='admin-complete-generic@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.category = 'Premium'
        self.model_obj.photo_url = 'https://example.com/generic-premium.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/generic-premium.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose-premium.jpg'
        self.model_obj.short_card_photo_url = ''
        self.model_obj.save(update_fields=['category', 'photo_url', 'long_card_photo_url', 'loose_photo_url', 'short_card_photo_url'])
        self.client.force_login(admin)

        response = self.client.get(reverse('catalog:complete-images'))

        self.assertContains(response, '1970 Pontiac Firebird')

    def test_complete_images_view_supports_verified_filter(self):
        admin = User.objects.create_user(
            email='admin-complete-filter@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.photo_url = ''
        self.model_obj.images_verified_at = timezone.now()
        self.model_obj.images_verified_by = admin
        self.model_obj.save(
            update_fields=[
                'short_card_photo_url',
                'long_card_photo_url',
                'loose_photo_url',
                'photo_url',
                'images_verified_at',
                'images_verified_by',
            ]
        )
        other = HotWheelsModel.objects.create(
            app_id='complete-filter-other',
            brand='Hot Wheels',
            toy='HCT88',
            number='088',
            model_name='Unverified Complete Car',
            year=2024,
            category='Mainline',
            photo_url='',
            short_card_photo_url='https://example.com/short-2.jpg',
            long_card_photo_url='https://example.com/long-2.jpg',
            loose_photo_url='https://example.com/loose-2.jpg',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('catalog:complete-images'), {'verified': 'unverified'})

        self.assertContains(response, other.model_name)
        self.assertNotContains(response, self.model_obj.model_name)

    def test_staff_can_toggle_image_verification(self):
        admin = User.objects.create_user(
            email='admin-toggle-verify@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.short_card_photo_url = 'https://example.com/short.jpg'
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.loose_photo_url = 'https://example.com/loose.jpg'
        self.model_obj.photo_url = ''
        self.model_obj.save(update_fields=['short_card_photo_url', 'long_card_photo_url', 'loose_photo_url', 'photo_url'])
        self.client.force_login(admin)

        response = self.client.post(
            reverse('catalog:toggle-image-verification', args=[self.model_obj.pk]),
            {'next': reverse('catalog:model-detail', args=[self.model_obj.pk])},
        )

        self.assertRedirects(response, reverse('catalog:model-detail', args=[self.model_obj.pk]))
        self.model_obj.refresh_from_db()
        self.assertIsNotNone(self.model_obj.images_verified_at)
        self.assertEqual(self.model_obj.images_verified_by, admin)

    def test_assigned_images_view_supports_year_series_and_sort_filters(self):
        admin = User.objects.create_user(
            email='admin7@example.com',
            password='ComplexPass123',
            is_staff=True,
        )
        self.model_obj.long_card_photo_url = 'https://example.com/long.jpg'
        self.model_obj.save(update_fields=['long_card_photo_url'])
        HotWheelsModel.objects.create(
            app_id='assigned-2',
            brand='Hot Wheels',
            toy='HCT22',
            number='022',
            model_name='Older Assigned',
            year=2020,
            category='Mainline',
            series='HW Drift',
            long_card_photo_url='https://example.com/older-long.jpg',
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('catalog:assigned-images'), {
            'year': '2022',
            'series': 'HW Dream Garage',
            'sort': 'name',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1970 Pontiac Firebird')
        self.assertNotContains(response, 'Older Assigned')
        self.assertContains(response, 'value="2022" selected')
        self.assertContains(response, 'value="HW Dream Garage" selected')

    def test_non_staff_cannot_open_assigned_images_view(self):
        user = User.objects.create_user(
            email='user2@example.com',
            password='ComplexPass123',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('catalog:assigned-images'))

        self.assertEqual(response.status_code, 403)

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


class CatalogScopeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='scope@example.com', password='ComplexPass123', login='scopeuser')
        HotWheelsModel.objects.create(
            app_id='scope-1',
            brand='Hot Wheels',
            toy='AAA01',
            number='001',
            model_name='Premium Supra',
            year=2025,
            category='Premium',
            series='Car Culture',
            series_number='1/5',
            photo_url='https://example.com/supra.jpg',
        )
        HotWheelsModel.objects.create(
            app_id='scope-2',
            brand='Hot Wheels',
            toy='AAA02',
            number='002',
            model_name='RLC Camaro',
            year=2025,
            category='RLC',
            series='2025 RLC Exclusive',
            series_number='',
            photo_url='https://example.com/camaro.jpg',
        )
        HotWheelsModel.objects.create(
            app_id='scope-3',
            brand='Matchbox',
            toy='MBX01',
            number='003',
            model_name='Matchbox Porsche',
            year=2025,
            category='Collectors',
            series='Matchbox Collectors',
            series_number='3/6',
            photo_url='https://example.com/porsche.jpg',
        )

    def test_catalog_uses_user_scope_by_default_when_enabled(self):
        self.user.catalog_scope_enabled = True
        self.user.catalog_scope_brands = ['Hot Wheels']
        self.user.catalog_scope_categories = ['Premium']
        self.user.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse('catalog:model-list'))

        self.assertContains(response, 'Premium Supra')
        self.assertNotContains(response, 'RLC Camaro')
        self.assertNotContains(response, 'Matchbox Porsche')
        self.assertEqual(response.context['selected_scope'], 'profile')

    def test_catalog_can_switch_back_to_full_view(self):
        self.user.catalog_scope_enabled = True
        self.user.catalog_scope_brands = ['Hot Wheels']
        self.user.catalog_scope_categories = ['Premium']
        self.user.save()
        self.client.force_login(self.user)

        response = self.client.get(reverse('catalog:model-list'), {'scope': 'all'})

        self.assertContains(response, 'Premium Supra')
        self.assertContains(response, 'RLC Camaro')
        self.assertContains(response, 'Matchbox Porsche')
        self.assertEqual(response.context['selected_scope'], 'all')

    def test_catalog_scope_can_filter_by_year_range(self):
        self.user.catalog_scope_enabled = True
        self.user.catalog_scope_brands = ['Hot Wheels']
        self.user.catalog_scope_year_from = 2025
        self.user.catalog_scope_year_to = 2025
        self.user.save()
        older_model = HotWheelsModel.objects.create(
            app_id='scope-4',
            brand='Hot Wheels',
            toy='AAA03',
            number='004',
            model_name='Old Firebird',
            year=2024,
            category='Premium',
            series='Retro',
            series_number='4/5',
            photo_url='https://example.com/old.jpg',
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('catalog:model-list'))

        self.assertContains(response, 'Premium Supra')
        self.assertNotContains(response, older_model.model_name)
