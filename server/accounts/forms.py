from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import AVATAR_CHOICES, User


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autofocus': True}))


class UserRegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('email', 'display_name', 'first_name', 'last_name')


class ProfileForm(forms.ModelForm):
    avatar_key = forms.ChoiceField(
        choices=AVATAR_CHOICES,
        widget=forms.RadioSelect,
        label='Avatar',
    )

    class Meta:
        model = User
        fields = ('display_name', 'first_name', 'last_name', 'bio', 'avatar_key')
