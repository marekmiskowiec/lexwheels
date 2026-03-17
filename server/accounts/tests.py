from django.test import TestCase
from django.urls import reverse

from .models import User


class AccountTests(TestCase):
    def test_register_creates_user(self):
        response = self.client.post(reverse('accounts:register'), {
            'email': 'test@example.com',
            'display_name': 'Tester',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'ComplexPass123',
            'password2': 'ComplexPass123',
        })
        self.assertRedirects(response, reverse('collections:dashboard'))
        self.assertTrue(User.objects.filter(email='test@example.com').exists())

    def test_profile_update(self):
        user = User.objects.create_user(email='test@example.com', password='ComplexPass123')
        self.client.force_login(user)
        response = self.client.post(reverse('accounts:profile-edit'), {
            'display_name': 'Lex',
            'first_name': 'Test',
            'last_name': 'User',
            'bio': 'Collector profile',
        })
        self.assertRedirects(response, reverse('accounts:profile'))
        user.refresh_from_db()
        self.assertEqual(user.display_name, 'Lex')

    def test_public_profile_visible(self):
        user = User.objects.create_user(email='test@example.com', password='ComplexPass123', display_name='Lex')
        response = self.client.get(reverse('accounts:public-profile', args=[user.pk]))
        self.assertContains(response, 'Lex')
