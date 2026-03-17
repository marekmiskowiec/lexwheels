from django.test import TestCase
from django.urls import reverse
from django.utils.formats import date_format
from django.utils import timezone

from .models import User


class AccountTests(TestCase):
    def test_register_creates_user(self):
        response = self.client.post(reverse('accounts:register'), {
            'email': 'test@example.com',
            'login': 'tester',
            'display_name': 'Tester',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'ComplexPass123',
            'password2': 'ComplexPass123',
        })
        self.assertRedirects(response, reverse('collections:dashboard'))
        self.assertTrue(User.objects.filter(email='test@example.com').exists())
        self.assertTrue(User.objects.filter(login='tester').exists())

    def test_profile_update(self):
        user = User.objects.create_user(email='test@example.com', password='ComplexPass123')
        self.client.force_login(user)
        response = self.client.post(reverse('accounts:profile-edit'), {
            'login': 'lex',
            'display_name': 'Lex',
            'first_name': 'Test',
            'last_name': 'User',
            'bio': 'Collector profile',
            'avatar_key': 'garage-blue',
        })
        self.assertRedirects(response, reverse('accounts:profile'))
        user.refresh_from_db()
        self.assertEqual(user.login, 'lex')
        self.assertEqual(user.display_name, 'Lex')
        self.assertEqual(user.avatar_key, 'garage-blue')

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
