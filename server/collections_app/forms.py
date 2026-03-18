from django import forms

from catalog.models import HotWheelsModel

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


class CollectionItemMultiVariantForm(forms.Form):
    model = forms.ModelChoiceField(queryset=HotWheelsModel.objects.none(), label='Model')

    def __init__(self, *args, **kwargs):
        collection = kwargs.pop('collection')
        super().__init__(*args, **kwargs)
        self.collection = collection
        self.fields['model'].queryset = HotWheelsModel.objects.all()
        self.variant_sections = []

        for packaging_value, packaging_label in CollectionItem.PACKAGING_CHOICES:
            enabled_name = f'enabled_{packaging_value}'
            quantity_name = f'quantity_{packaging_value}'
            condition_name = f'condition_{packaging_value}'

            self.fields[enabled_name] = forms.BooleanField(required=False, label=packaging_label)
            self.fields[quantity_name] = forms.IntegerField(required=False, min_value=1, initial=1, label='Ilość')
            self.fields[condition_name] = forms.ChoiceField(
                required=False,
                choices=CollectionItem.CONDITION_CHOICES,
                initial='good',
                label='Stan',
            )
            self.variant_sections.append(
                {
                    'packaging_value': packaging_value,
                    'packaging_label': packaging_label,
                    'enabled': self[enabled_name],
                    'quantity': self[quantity_name],
                    'condition': self[condition_name],
                }
            )

    def clean(self):
        cleaned_data = super().clean()
        model = cleaned_data.get('model')
        selected_variants = []

        for packaging_value, _ in CollectionItem.PACKAGING_CHOICES:
            if not cleaned_data.get(f'enabled_{packaging_value}'):
                continue

            quantity = cleaned_data.get(f'quantity_{packaging_value}')
            condition = cleaned_data.get(f'condition_{packaging_value}')
            if not quantity:
                self.add_error(f'quantity_{packaging_value}', 'Podaj ilość dla zaznaczonego wariantu.')
                continue
            if not condition:
                self.add_error(f'condition_{packaging_value}', 'Wybierz stan dla zaznaczonego wariantu.')
                continue
            selected_variants.append((packaging_value, quantity, condition))

        if not selected_variants:
            raise forms.ValidationError('Zaznacz przynajmniej jeden wariant modelu do dodania.')

        if model:
            for packaging_value, _, condition in selected_variants:
                if CollectionItem.objects.filter(
                    collection=self.collection,
                    model=model,
                    packaging_state=packaging_value,
                    condition=condition,
                ).exists():
                    self.add_error(
                        None,
                        f'Wariant "{dict(CollectionItem.PACKAGING_CHOICES)[packaging_value]}" w stanie "{dict(CollectionItem.CONDITION_CHOICES)[condition]}" już istnieje w tej kolekcji.',
                    )

        cleaned_data['selected_variants'] = selected_variants
        return cleaned_data

    def save(self):
        model = self.cleaned_data['model']
        created_items = []
        for packaging_value, quantity, condition in self.cleaned_data['selected_variants']:
            created_items.append(
                CollectionItem.objects.create(
                    collection=self.collection,
                    model=model,
                    packaging_state=packaging_value,
                    quantity=quantity,
                    condition=condition,
                )
            )
        return created_items


class CollectionBatchAddForm(forms.Form):
    collection = forms.ModelChoiceField(queryset=Collection.objects.none(), label='Dodaj do kolekcji')
    next = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        owner = kwargs.pop('owner')
        super().__init__(*args, **kwargs)
        self.fields['collection'].queryset = Collection.objects.filter(owner=owner).order_by('kind', 'name')
