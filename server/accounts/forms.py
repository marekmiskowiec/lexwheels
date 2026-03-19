from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from catalog.models import HotWheelsModel

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
    catalog_scope_brands = forms.MultipleChoiceField(
        required=False,
        widget=forms.SelectMultiple,
        label='Pokazuj tylko marki',
        help_text='Pozostaw puste, aby nie ograniczać marek.',
    )
    catalog_scope_categories = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Pokazuj tylko kategorie',
        help_text='Pozostaw puste, aby nie ograniczać kategorii.',
    )
    catalog_scope_year_from = forms.ChoiceField(required=False)
    catalog_scope_year_to = forms.ChoiceField(required=False)

    class Meta:
        model = User
        fields = (
            'display_name',
            'bio',
            'avatar_key',
            'catalog_scope_enabled',
            'catalog_scope_brands',
            'catalog_scope_categories',
            'catalog_scope_year_from',
            'catalog_scope_year_to',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        brand_choices = [
            (brand, brand)
            for brand in HotWheelsModel.objects.exclude(brand='').values_list('brand', flat=True).distinct().order_by('brand')
        ]
        category_choices = [
            (category, category)
            for category in HotWheelsModel.objects.exclude(category='').values_list('category', flat=True).distinct().order_by('category')
        ]
        year_choices = [
            (str(year), str(year))
            for year in HotWheelsModel.objects.exclude(year__isnull=True).values_list('year', flat=True).distinct().order_by('year')
        ]

        self.fields['catalog_scope_enabled'].label = 'Domyślnie używaj mojego zakresu w katalogu'
        self.fields['catalog_scope_year_from'].label = 'Rok od'
        self.fields['catalog_scope_year_to'].label = 'Rok do'
        self.fields['catalog_scope_year_from'].help_text = 'Opcjonalne ograniczenie dolnej granicy rocznika.'
        self.fields['catalog_scope_year_to'].help_text = 'Opcjonalne ograniczenie górnej granicy rocznika.'
        self.fields['catalog_scope_brands'].choices = brand_choices
        self.fields['catalog_scope_categories'].choices = category_choices
        self.fields['catalog_scope_year_from'].choices = [('', 'Bez ograniczenia')] + year_choices
        self.fields['catalog_scope_year_to'].choices = [('', 'Bez ograniczenia')] + year_choices
        self.initial['catalog_scope_year_from'] = str(self.instance.catalog_scope_year_from or '')
        self.initial['catalog_scope_year_to'] = str(self.instance.catalog_scope_year_to or '')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.display_name = self.cleaned_data['display_name']
        user.login = self.cleaned_data['display_name']
        user.catalog_scope_brands = User.normalize_scope_values(self.cleaned_data.get('catalog_scope_brands'))
        user.catalog_scope_categories = User.normalize_scope_values(self.cleaned_data.get('catalog_scope_categories'))
        user.catalog_scope_year_from = int(self.cleaned_data['catalog_scope_year_from']) if self.cleaned_data['catalog_scope_year_from'] else None
        user.catalog_scope_year_to = int(self.cleaned_data['catalog_scope_year_to']) if self.cleaned_data['catalog_scope_year_to'] else None
        if commit:
            user.save()
        return user
