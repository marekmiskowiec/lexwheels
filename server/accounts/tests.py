from django.test import TestCase
from django.urls import reverse
from django.utils.formats import date_format
from django.utils import timezone

from catalog.models import HotWheelsModel

from .forms import ProfileForm
from .models import User


class AccountTests(TestCase):
    def setUp(self):
        HotWheelsModel.objects.create(
            app_id='profile-test-1',
            brand='Hot Wheels',
            toy='HCT05',
            number='001',
            model_name='1970 Pontiac Firebird',
            year=2022,
            category='Mainline',
            series='HW Dream Garage',
            series_number='1/5',
            photo_url='https://example.com/firebird.jpg',
        )
        HotWheelsModel.objects.create(
            app_id='profile-test-2',
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

    def test_register_creates_user(self):
        response = self.client.post(reverse('accounts:register'), {
            'email': 'test@example.com',
            'display_name': 'Tester',
            'password1': 'ComplexPass123',
            'password2': 'ComplexPass123',
        })
        self.assertRedirects(response, reverse('collections:dashboard'))
        self.assertTrue(User.objects.filter(email='test@example.com').exists())
        self.assertTrue(User.objects.filter(login='Tester', display_name='Tester').exists())

    def test_profile_update(self):
        user = User.objects.create_user(email='test@example.com', password='ComplexPass123')
        self.client.force_login(user)
        response = self.client.post(reverse('accounts:profile-edit'), {
            'display_name': 'Lex',
            'bio': 'Collector profile',
            'youtube_url': 'https://www.youtube.com/@lexwheels',
            'tiktok_url': 'https://www.tiktok.com/@lexwheels',
            'instagram_url': 'https://www.instagram.com/lexwheels/',
            'avatar_key': 'garage-blue',
            'catalog_scope_enabled': 'on',
            'catalog_scope_brands': ['Hot Wheels'],
            'catalog_scope_categories': ['Mainline'],
            'catalog_scope_year_from': '2022',
            'catalog_scope_year_to': '2023',
        })
        self.assertRedirects(response, reverse('accounts:profile'))
        user.refresh_from_db()
        self.assertEqual(user.login, 'Lex')
        self.assertEqual(user.display_name, 'Lex')
        self.assertEqual(user.avatar_key, 'garage-blue')
        self.assertEqual(user.youtube_url, 'https://www.youtube.com/@lexwheels')
        self.assertEqual(user.tiktok_url, 'https://www.tiktok.com/@lexwheels')
        self.assertEqual(user.instagram_url, 'https://www.instagram.com/lexwheels/')
        self.assertTrue(user.catalog_scope_enabled)
        self.assertEqual(user.catalog_scope_brands, ['Hot Wheels'])
        self.assertEqual(user.catalog_scope_categories, ['Mainline'])
        self.assertEqual(user.catalog_scope_year_from, 2022)
        self.assertEqual(user.catalog_scope_year_to, 2023)

    def test_profile_form_rejects_non_youtube_domain(self):
        user = User.objects.create_user(email='test@example.com', password='ComplexPass123')

        form = ProfileForm(
            data={
                'display_name': 'Lex',
                'bio': '',
                'youtube_url': 'https://example.com/channel/test',
                'tiktok_url': '',
                'instagram_url': '',
                'avatar_key': 'garage-blue',
                'catalog_scope_brands': [],
                'catalog_scope_categories': [],
                'catalog_scope_year_from': '',
                'catalog_scope_year_to': '',
            },
            instance=user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('youtube_url', form.errors)

    def test_profile_form_rejects_non_tiktok_domain(self):
        user = User.objects.create_user(email='test2@example.com', password='ComplexPass123')

        form = ProfileForm(
            data={
                'display_name': 'LexTwo',
                'bio': '',
                'youtube_url': '',
                'tiktok_url': 'https://example.com/@lexwheels',
                'instagram_url': '',
                'avatar_key': 'garage-blue',
                'catalog_scope_brands': [],
                'catalog_scope_categories': [],
                'catalog_scope_year_from': '',
                'catalog_scope_year_to': '',
            },
            instance=user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('tiktok_url', form.errors)

    def test_profile_form_rejects_non_instagram_domain(self):
        user = User.objects.create_user(email='test3@example.com', password='ComplexPass123')

        form = ProfileForm(
            data={
                'display_name': 'LexThree',
                'bio': '',
                'youtube_url': '',
                'tiktok_url': '',
                'instagram_url': 'https://example.com/lexwheels',
                'avatar_key': 'garage-blue',
                'catalog_scope_brands': [],
                'catalog_scope_categories': [],
                'catalog_scope_year_from': '',
                'catalog_scope_year_to': '',
            },
            instance=user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('instagram_url', form.errors)

    def test_profile_update_keeps_display_name_and_login_in_sync(self):
        user = User.objects.create_user(email='test@example.com', login='Start', password='ComplexPass123')
        self.client.force_login(user)

        response = self.client.post(reverse('accounts:profile-edit'), {
            'display_name': 'NowyLogin',
            'bio': 'Collector profile',
            'avatar_key': 'garage-blue',
            'catalog_scope_brands': [],
            'catalog_scope_categories': [],
        })

        self.assertRedirects(response, reverse('accounts:profile'))
        user.refresh_from_db()
        self.assertEqual(user.display_name, 'NowyLogin')
        self.assertEqual(user.login, 'NowyLogin')

    def test_profile_form_rejects_bio_longer_than_100_characters(self):
        user = User.objects.create_user(email='bio@example.com', password='ComplexPass123')

        form = ProfileForm(
            data={
                'display_name': 'BioUser',
                'bio': 'a' * 101,
                'youtube_url': '',
                'tiktok_url': '',
                'instagram_url': '',
                'avatar_key': 'garage-blue',
                'catalog_scope_brands': [],
                'catalog_scope_categories': [],
                'catalog_scope_year_from': '',
                'catalog_scope_year_to': '',
            },
            instance=user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('bio', form.errors)

    def test_public_profile_visible(self):
        user = User.objects.create_user(email='test@example.com', password='ComplexPass123', display_name='Lex')
        response = self.client.get(reverse('accounts:public-profile', args=[user.pk]))
        self.assertContains(response, 'Lex')

    def test_public_collectors_list_shows_collectors_with_public_content(self):
        user = User.objects.create_user(email='test@example.com', password='ComplexPass123', display_name='Lex')
        from collections_app.models import Collection
        Collection.objects.create(
            owner=user,
            name='Publiczna',
            kind=Collection.KIND_OWNED,
            visibility=Collection.VISIBILITY_PUBLIC,
        )
        response = self.client.get(reverse('accounts:collector-list'))
        self.assertContains(response, 'Lex')
        self.assertContains(response, f'Dołączył: {date_format(timezone.localtime(user.date_joined), "j E Y", use_l10n=True)}')
        self.assertNotContains(response, user.email)

    def test_profile_renders_selected_avatar(self):
        user = User.objects.create_user(
            email='test@example.com',
            password='ComplexPass123',
            display_name='Lex',
            avatar_key='teal-speed',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('accounts:profile'))
        self.assertContains(response, 'accounts/avatars/teal-speed')

    def test_profile_shows_registration_date_instead_of_email(self):
        user = User.objects.create_user(email='test@example.com', login='tester', password='ComplexPass123')
        self.client.force_login(user)
        joined_label = date_format(timezone.localtime(user.date_joined), 'j E Y', use_l10n=True)

        response = self.client.get(reverse('accounts:profile'))

        self.assertContains(response, f'Dołączył: {joined_label}')

    def test_user_can_log_in_with_email(self):
        user = User.objects.create_user(email='test@example.com', login='tester', password='ComplexPass123')
        response = self.client.post(reverse('login'), {
            'username': user.email,
            'password': 'ComplexPass123',
        })
        self.assertRedirects(response, reverse('collections:dashboard'))

    def test_user_can_log_in_with_login(self):
        user = User.objects.create_user(email='test@example.com', login='tester', password='ComplexPass123')
        response = self.client.post(reverse('login'), {
            'username': user.login,
            'password': 'ComplexPass123',
        })
        self.assertRedirects(response, reverse('collections:dashboard'))

    def test_authenticated_navigation_shows_login_instead_of_email(self):
        user = User.objects.create_user(email='test@example.com', login='tester', password='ComplexPass123')
        self.client.force_login(user)

        response = self.client.get(reverse('collections:dashboard'))

        self.assertContains(response, user.login)
        self.assertNotContains(response, user.email)

    def test_profile_edit_shows_catalog_scope_fields(self):
        user = User.objects.create_user(email='test@example.com', login='tester', password='ComplexPass123')
        self.client.force_login(user)

        response = self.client.get(reverse('accounts:profile-edit'))

        self.assertContains(response, 'Domyślnie używaj mojego zakresu w katalogu')
        self.assertContains(response, 'Pokazuj tylko marki')
        self.assertNotContains(response, 'Ukryj kategorie')
        self.assertContains(response, 'value="2022"')
        self.assertContains(response, 'value="2023"')
        self.assertContains(response, 'type="checkbox"')
        self.assertContains(response, 'Mainline')
        self.assertContains(response, 'Collectors')
