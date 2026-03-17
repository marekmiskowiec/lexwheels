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


class CollectionBatchAddForm(forms.Form):
    collection = forms.ModelChoiceField(queryset=Collection.objects.none(), label='Dodaj do kolekcji')
    next = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        owner = kwargs.pop('owner')
        super().__init__(*args, **kwargs)
        self.fields['collection'].queryset = Collection.objects.filter(owner=owner).order_by('kind', 'name')
