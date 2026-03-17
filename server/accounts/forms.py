from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import AVATAR_CHOICES, User


class LoginNormalizationMixin:
    def clean_display_name(self):
        display_name = User.objects.normalize_login(self.cleaned_data['display_name'])
        if not display_name:
            raise forms.ValidationError('Podaj nazwę użytkownika.')
        queryset = User.objects.filter(login__iexact=display_name)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError('Ta nazwa użytkownika jest już zajęta.')
        return display_name


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label='Email lub login',
        widget=forms.TextInput(attrs={'autofocus': True, 'autocomplete': 'username'}),
    )


class UserRegistrationForm(LoginNormalizationMixin, UserCreationForm):
    display_name = forms.CharField(
        label='Nazwa użytkownika',
        help_text='Ta sama nazwa będzie używana do wyświetlania profilu i logowania.',
    )

    class Meta:
        model = User
        fields = ('email', 'display_name')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.display_name = self.cleaned_data['display_name']
        user.login = self.cleaned_data['display_name']
        if commit:
            user.save()
        return user


class ProfileForm(LoginNormalizationMixin, forms.ModelForm):
    display_name = forms.CharField(
        label='Nazwa użytkownika',
        help_text='Ta sama nazwa będzie używana do wyświetlania profilu i logowania.',
    )
    avatar_key = forms.ChoiceField(
        choices=AVATAR_CHOICES,
        widget=forms.RadioSelect,
        label='Avatar',
    )

    class Meta:
        model = User
        fields = ('display_name', 'bio', 'avatar_key')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.display_name = self.cleaned_data['display_name']
        user.login = self.cleaned_data['display_name']
        if commit:
            user.save()
        return user
