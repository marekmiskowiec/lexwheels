from django import forms
from django.db.models import Q

from catalog.models import HotWheelsModel

from .models import Collection, CollectionItem


class CatalogModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.model_name} | {obj.brand or "-"} | {obj.year or "-"} | Toy: {obj.toy} | Number: {obj.number}'


class CollectionForm(forms.ModelForm):
    class Meta:
        model = Collection
        fields = ('name', 'description', 'kind', 'visibility')


class VariantSectionsMixin:
    def build_variant_sections(self):
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

    def collect_selected_variants(self):
        selected_variants = []

        for packaging_value, _ in CollectionItem.PACKAGING_CHOICES:
            if not self.cleaned_data.get(f'enabled_{packaging_value}'):
                continue

            quantity = self.cleaned_data.get(f'quantity_{packaging_value}')
            condition = self.cleaned_data.get(f'condition_{packaging_value}')
            if not quantity:
                self.add_error(f'quantity_{packaging_value}', 'Podaj ilość dla zaznaczonego wariantu.')
                continue
            if not condition:
                self.add_error(f'condition_{packaging_value}', 'Wybierz stan dla zaznaczonego wariantu.')
                continue
            selected_variants.append((packaging_value, quantity, condition))

        return selected_variants


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


class CollectionItemMultiVariantForm(VariantSectionsMixin, forms.Form):
    model = CatalogModelChoiceField(queryset=HotWheelsModel.objects.none(), label='Model')

    def __init__(self, *args, **kwargs):
        collection = kwargs.pop('collection')
        model_query = kwargs.pop('model_query', '')
        selected_model_id = kwargs.pop('selected_model_id', '')
        super().__init__(*args, **kwargs)
        self.collection = collection
        self.model_query = (model_query or '').strip()

        queryset = HotWheelsModel.objects.none()
        selected_model = None
        if selected_model_id:
            selected_model = HotWheelsModel.objects.filter(pk=selected_model_id).first()

        if self.model_query:
            result_ids = list(
                HotWheelsModel.objects.filter(
                    Q(model_name__icontains=self.model_query)
                    | Q(toy__icontains=self.model_query)
                    | Q(number__icontains=self.model_query)
                    | Q(brand__icontains=self.model_query)
                    | Q(series__icontains=self.model_query)
                ).order_by('brand', 'year', 'number', 'model_name').values_list('pk', flat=True)[:100]
            )
            if selected_model and selected_model.pk not in result_ids:
                result_ids.append(selected_model.pk)
            queryset = HotWheelsModel.objects.filter(pk__in=result_ids).order_by('brand', 'year', 'number', 'model_name')
        elif selected_model:
            queryset = HotWheelsModel.objects.filter(pk=selected_model.pk)

        self.fields['model'].queryset = queryset
        self.fields['model'].empty_label = 'Wybierz model z wyników wyszukiwania'
        self.build_variant_sections()

    def clean(self):
        cleaned_data = super().clean()
        model = cleaned_data.get('model')
        selected_variants = self.collect_selected_variants()

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


class CatalogQuickAddForm(VariantSectionsMixin, forms.Form):
    collection = forms.ModelChoiceField(queryset=Collection.objects.none(), label='Dodaj do kolekcji')
    model = forms.ModelChoiceField(queryset=HotWheelsModel.objects.none(), widget=forms.HiddenInput)
    next = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        owner = kwargs.pop('owner')
        super().__init__(*args, **kwargs)
        self.fields['collection'].queryset = Collection.objects.filter(owner=owner).order_by('kind', 'name')
        self.fields['model'].queryset = HotWheelsModel.objects.all()
        self.build_variant_sections()

    def clean(self):
        cleaned_data = super().clean()
        collection = cleaned_data.get('collection')
        model = cleaned_data.get('model')
        selected_variants = self.collect_selected_variants()

        if not selected_variants:
            raise forms.ValidationError('Zaznacz przynajmniej jeden wariant modelu do dodania.')

        if collection and model:
            for packaging_value, _, condition in selected_variants:
                if CollectionItem.objects.filter(
                    collection=collection,
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
        collection = self.cleaned_data['collection']
        model = self.cleaned_data['model']
        created_items = []
        for packaging_value, quantity, condition in self.cleaned_data['selected_variants']:
            created_items.append(
                CollectionItem.objects.create(
                    collection=collection,
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


class CollectionBulkEditForm(forms.Form):
    quantity = forms.IntegerField(required=False, min_value=1, label='Nowa ilość')
    condition = forms.ChoiceField(
        required=False,
        choices=(('', 'Bez zmian'),) + CollectionItem.CONDITION_CHOICES,
        label='Nowy stan',
    )
    packaging_state = forms.ChoiceField(
        required=False,
        choices=(('', 'Bez zmian'),) + CollectionItem.PACKAGING_CHOICES,
        label='Nowe opakowanie',
    )

    def __init__(self, *args, **kwargs):
        collection = kwargs.pop('collection')
        super().__init__(*args, **kwargs)
        self.collection = collection

    def clean(self):
        cleaned_data = super().clean()
        if not any(cleaned_data.get(field_name) for field_name in ('quantity', 'condition', 'packaging_state')):
            raise forms.ValidationError('Wybierz przynajmniej jedną zmianę do zastosowania.')
        return cleaned_data

    def apply(self, items):
        updated_count = 0
        for item in items.select_related('model'):
            new_quantity = self.cleaned_data.get('quantity') or item.quantity
            new_condition = self.cleaned_data.get('condition') or item.condition
            new_packaging = self.cleaned_data.get('packaging_state') or item.packaging_state

            duplicate_exists = CollectionItem.objects.filter(
                collection=self.collection,
                model=item.model,
                packaging_state=new_packaging,
                condition=new_condition,
            ).exclude(pk=item.pk).exists()
            if duplicate_exists:
                continue

            if (
                new_quantity != item.quantity
                or new_condition != item.condition
                or new_packaging != item.packaging_state
            ):
                item.quantity = new_quantity
                item.condition = new_condition
                item.packaging_state = new_packaging
                item.save(update_fields=['quantity', 'condition', 'packaging_state'])
                updated_count += 1

        return updated_count
