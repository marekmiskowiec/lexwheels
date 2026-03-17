from django.test import TestCase
from django.urls import reverse

from .models import User


class AccountTests(TestCase):
    def test_register_creates_user(self):
        response = self.client.post(reverse('accounts:register'), {
            'email': 'test@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'ComplexPass123',
            'password2': 'ComplexPass123',
        })
        self.assertRedirects(response, reverse('collections:dashboard'))
        self.assertTrue(User.objects.filter(email='test@example.com').exists())
