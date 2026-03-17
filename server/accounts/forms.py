from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import AVATAR_CHOICES, User


class LoginNormalizationMixin:
    def clean_login(self):
        return User.objects.normalize_login(self.cleaned_data['login'])


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label='Email lub login',
        widget=forms.TextInput(attrs={'autofocus': True, 'autocomplete': 'username'}),
    )


class UserRegistrationForm(LoginNormalizationMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ('email', 'login', 'display_name')


class ProfileForm(LoginNormalizationMixin, forms.ModelForm):
    avatar_key = forms.ChoiceField(
        choices=AVATAR_CHOICES,
        widget=forms.RadioSelect,
        label='Avatar',
    )

    class Meta:
        model = User
        fields = ('login', 'display_name', 'bio', 'avatar_key')
