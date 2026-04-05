from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import HotWheelsModel
from collections_app.models import Collection, CollectionItem


class HomeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='collector@example.com', password='ComplexPass123', login='collector')
        self.model_obj = HotWheelsModel.objects.create(
            app_id='home-001',
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

    def test_home_page_uses_dedicated_template_for_guests(self):
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')
        self.assertContains(response, 'Zacznij od kolekcji, nie od listy modeli.')
        self.assertContains(response, 'Na blogu')
        self.assertContains(response, 'Jak czytać case mixy bez chaosu')
        self.assertContains(response, reverse('catalog:model-list'))

    def test_home_page_shows_authenticated_dashboard_summary(self):
        collection = Collection.objects.create(owner=self.user, name='Moja kolekcja', kind=Collection.KIND_OWNED)
        CollectionItem.objects.create(collection=collection, model=self.model_obj, quantity=2, packaging_state='short_card')
        self.client.force_login(self.user)

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LexWheels dla')
        self.assertContains(response, 'Stan kolekcji')
        self.assertContains(response, 'Najbliżej ukończenia')
        self.assertContains(response, 'Moja kolekcja')

    def test_catalog_stays_available_under_catalog_path(self):
        response = self.client.get(reverse('catalog:model-list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Katalog')
