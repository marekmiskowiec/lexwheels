import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import HotWheelsModel


class ImportModelsCommandTests(TestCase):
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


class CatalogViewTests(TestCase):
    def setUp(self):
        self.model_obj = HotWheelsModel.objects.create(
            app_id='abc123',
            toy='HCT05',
            number='001',
            model_name='1970 Pontiac Firebird',
            series='HW Dream Garage',
            series_number='1/5',
            photo_url='https://example.com/car.jpg',
        )

    def test_catalog_search(self):
        response = self.client.get(reverse('catalog:model-list'), {'q': 'Firebird'})
        self.assertContains(response, '1970 Pontiac Firebird')

    def test_model_detail(self):
        response = self.client.get(reverse('catalog:model-detail', args=[self.model_obj.pk]))
        self.assertContains(response, 'HCT05')
