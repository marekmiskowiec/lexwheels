from django import forms

from .models import Collection, CollectionItem


class CollectionForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = ('name', 'description', 'kind', 'visibility')


class CollectionItemForm(forms.ModelForm):
    acquired_at = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    class Meta:
        model = CollectionItem
        fields = (
            'model',
            'quantity',
            'condition',
            'packaging_state',
            'acquired_at',
            'notes',
            'is_favorite',
        )
