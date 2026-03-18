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

    def clean(self):
        cleaned_data = super().clean()
        model = cleaned_data.get('model')
        packaging_state = cleaned_data.get('packaging_state')
        condition = cleaned_data.get('condition')
        if not all([model, packaging_state, condition]):
            return cleaned_data

        collection = getattr(self.instance, 'collection', None) or getattr(self, 'collection', None)
        if collection is None:
            return cleaned_data

        queryset = CollectionItem.objects.filter(
            collection=collection,
            model=model,
            packaging_state=packaging_state,
            condition=condition,
        )
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError('Taki wariant modelu jest już w tej kolekcji.')
        return cleaned_data


class CollectionBatchAddForm(forms.Form):
    collection = forms.ModelChoiceField(queryset=Collection.objects.none(), label='Dodaj do kolekcji')
    next = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        owner = kwargs.pop('owner')
        super().__init__(*args, **kwargs)
        self.fields['collection'].queryset = Collection.objects.filter(owner=owner).order_by('kind', 'name')
