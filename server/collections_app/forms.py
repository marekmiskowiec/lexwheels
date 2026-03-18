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
    CARD_ATTRIBUTE_NAMES = (
        'is_sealed',
        'has_soft_corners',
        'has_protector',
        'is_signed',
        'has_bent_hook',
        'has_cracked_blister',
    )

    @classmethod
    def normalize_card_attributes(cls, packaging_value, payload):
        if packaging_value == 'loose':
            for field_name in cls.CARD_ATTRIBUTE_NAMES:
                payload[field_name] = False
        return payload

    def build_variant_sections(self, packaging_choices=None):
        self.packaging_choices = tuple(packaging_choices or CollectionItem.PACKAGING_CHOICES)
        self.variant_sections = []
        for packaging_value, packaging_label in self.packaging_choices:
            enabled_name = f'enabled_{packaging_value}'
            quantity_name = f'quantity_{packaging_value}'
            condition_name = f'condition_{packaging_value}'
            sealed_name = f'is_sealed_{packaging_value}'
            soft_corners_name = f'has_soft_corners_{packaging_value}'
            protector_name = f'has_protector_{packaging_value}'
            signed_name = f'is_signed_{packaging_value}'
            bent_hook_name = f'has_bent_hook_{packaging_value}'
            cracked_blister_name = f'has_cracked_blister_{packaging_value}'

            self.fields[enabled_name] = forms.BooleanField(required=False, label=packaging_label)
            self.fields[quantity_name] = forms.IntegerField(required=False, min_value=1, initial=1, label='Ilość')
            self.fields[condition_name] = forms.ChoiceField(
                required=False,
                choices=CollectionItem.CONDITION_CHOICES,
                initial='good',
                label='Stan',
            )
            self.fields[sealed_name] = forms.BooleanField(required=False, label='Sealed')
            self.fields[soft_corners_name] = forms.BooleanField(required=False, label='Soft corners')
            self.fields[protector_name] = forms.BooleanField(required=False, label='Protector')
            self.fields[signed_name] = forms.BooleanField(required=False, label='Signed')
            self.fields[bent_hook_name] = forms.BooleanField(required=False, label='Bent hook')
            self.fields[cracked_blister_name] = forms.BooleanField(required=False, label='Cracked blister')
            self.variant_sections.append(
                {
                    'packaging_value': packaging_value,
                    'packaging_label': packaging_label,
                    'supports_card_attributes': packaging_value != 'loose',
                    'enabled': self[enabled_name],
                    'quantity': self[quantity_name],
                    'condition': self[condition_name],
                    'is_sealed': self[sealed_name],
                    'has_soft_corners': self[soft_corners_name],
                    'has_protector': self[protector_name],
                    'is_signed': self[signed_name],
                    'has_bent_hook': self[bent_hook_name],
                    'has_cracked_blister': self[cracked_blister_name],
                }
            )

    def collect_selected_variants(self):
        selected_variants = []

        for packaging_value, _ in getattr(self, 'packaging_choices', CollectionItem.PACKAGING_CHOICES):
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
            selected_variants.append(
                self.normalize_card_attributes(
                    packaging_value,
                    {
                        'packaging_value': packaging_value,
                        'quantity': quantity,
                        'condition': condition,
                        'is_sealed': self.cleaned_data.get(f'is_sealed_{packaging_value}', False),
                        'has_soft_corners': self.cleaned_data.get(f'has_soft_corners_{packaging_value}', False),
                        'has_protector': self.cleaned_data.get(f'has_protector_{packaging_value}', False),
                        'is_signed': self.cleaned_data.get(f'is_signed_{packaging_value}', False),
                        'has_bent_hook': self.cleaned_data.get(f'has_bent_hook_{packaging_value}', False),
                        'has_cracked_blister': self.cleaned_data.get(f'has_cracked_blister_{packaging_value}', False),
                    },
                )
            )

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
            'is_sealed',
            'has_soft_corners',
            'has_protector',
            'is_signed',
            'has_bent_hook',
            'has_cracked_blister',
            'acquired_at',
            'notes',
            'is_favorite',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        model = getattr(self.instance, 'model', None) or self.initial.get('model')
        if model and hasattr(model, 'available_packaging_choices'):
            self.fields['packaging_state'].choices = model.available_packaging_choices
        current_packaging = getattr(self.instance, 'packaging_state', '') or self.initial.get('packaging_state')
        if current_packaging == 'loose':
            for field_name in self.CARD_ATTRIBUTE_NAMES:
                self.fields.pop(field_name, None)

    def clean(self):
        cleaned_data = super().clean()
        model = cleaned_data.get('model')
        packaging_state = cleaned_data.get('packaging_state')
        condition = cleaned_data.get('condition')
        if not all([model, packaging_state, condition]):
            return cleaned_data

        cleaned_data = self.normalize_card_attributes(packaging_state, cleaned_data)

        if packaging_state not in model.available_packaging_states:
            raise forms.ValidationError('Ten model nie występuje w wybranym typie opakowania.')

        collection = getattr(self.instance, 'collection', None) or getattr(self, 'collection', None)
        if collection is None:
            return cleaned_data

        queryset = CollectionItem.objects.filter(
            collection=collection,
            model=model,
            packaging_state=packaging_state,
            condition=condition,
            is_sealed=cleaned_data.get('is_sealed', False),
            has_soft_corners=cleaned_data.get('has_soft_corners', False),
            has_protector=cleaned_data.get('has_protector', False),
            is_signed=cleaned_data.get('is_signed', False),
            has_bent_hook=cleaned_data.get('has_bent_hook', False),
            has_cracked_blister=cleaned_data.get('has_cracked_blister', False),
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
        self.build_variant_sections(selected_model.available_packaging_choices if selected_model else None)

    def clean(self):
        cleaned_data = super().clean()
        model = cleaned_data.get('model')
        selected_variants = self.collect_selected_variants()

        if not selected_variants:
            raise forms.ValidationError('Zaznacz przynajmniej jeden wariant modelu do dodania.')

        if model:
            for variant in selected_variants:
                packaging_value = variant['packaging_value']
                condition = variant['condition']
                if packaging_value not in model.available_packaging_states:
                    self.add_error(None, 'Ten model nie występuje w wybranym typie opakowania.')
                    continue
                if CollectionItem.objects.filter(
                    collection=self.collection,
                    model=model,
                    packaging_state=packaging_value,
                    condition=condition,
                    is_sealed=variant['is_sealed'],
                    has_soft_corners=variant['has_soft_corners'],
                    has_protector=variant['has_protector'],
                    is_signed=variant['is_signed'],
                    has_bent_hook=variant['has_bent_hook'],
                    has_cracked_blister=variant['has_cracked_blister'],
                ).exists():
                    self.add_error(
                        None,
                        f'Wariant "{dict(CollectionItem.PACKAGING_CHOICES)[packaging_value]}" w stanie "{dict(CollectionItem.CONDITION_CHOICES)[condition]}" z wybranymi cechami już istnieje w tej kolekcji.',
                    )

        cleaned_data['selected_variants'] = selected_variants
        return cleaned_data

    def save(self):
        model = self.cleaned_data['model']
        created_items = []
        for variant in self.cleaned_data['selected_variants']:
            created_items.append(
                CollectionItem.objects.create(
                    collection=self.collection,
                    model=model,
                    packaging_state=variant['packaging_value'],
                    quantity=variant['quantity'],
                    condition=variant['condition'],
                    is_sealed=variant['is_sealed'],
                    has_soft_corners=variant['has_soft_corners'],
                    has_protector=variant['has_protector'],
                    is_signed=variant['is_signed'],
                    has_bent_hook=variant['has_bent_hook'],
                    has_cracked_blister=variant['has_cracked_blister'],
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
        self.condition_choices = CollectionItem.CONDITION_CHOICES
        self.build_variant_sections()

    def clean(self):
        cleaned_data = super().clean()
        collection = cleaned_data.get('collection')
        model = cleaned_data.get('model')
        selected_variants = self.collect_selected_variants()

        if not selected_variants:
            raise forms.ValidationError('Zaznacz przynajmniej jeden wariant modelu do dodania.')

        if collection and model:
            for variant in selected_variants:
                packaging_value = variant['packaging_value']
                condition = variant['condition']
                if packaging_value not in model.available_packaging_states:
                    self.add_error(
                        None,
                        f'Model "{model.model_name}" nie występuje w wariancie "{dict(CollectionItem.PACKAGING_CHOICES)[packaging_value]}".',
                    )
                    continue
                if CollectionItem.objects.filter(
                    collection=collection,
                    model=model,
                    packaging_state=packaging_value,
                    condition=condition,
                    is_sealed=variant['is_sealed'],
                    has_soft_corners=variant['has_soft_corners'],
                    has_protector=variant['has_protector'],
                    is_signed=variant['is_signed'],
                    has_bent_hook=variant['has_bent_hook'],
                    has_cracked_blister=variant['has_cracked_blister'],
                ).exists():
                    self.add_error(
                        None,
                        f'Wariant "{dict(CollectionItem.PACKAGING_CHOICES)[packaging_value]}" w stanie "{dict(CollectionItem.CONDITION_CHOICES)[condition]}" z wybranymi cechami już istnieje w tej kolekcji.',
                    )

        cleaned_data['selected_variants'] = selected_variants
        return cleaned_data

    def save(self):
        collection = self.cleaned_data['collection']
        model = self.cleaned_data['model']
        created_items = []
        for variant in self.cleaned_data['selected_variants']:
            created_items.append(
                CollectionItem.objects.create(
                    collection=collection,
                    model=model,
                    packaging_state=variant['packaging_value'],
                    quantity=variant['quantity'],
                    condition=variant['condition'],
                    is_sealed=variant['is_sealed'],
                    has_soft_corners=variant['has_soft_corners'],
                    has_protector=variant['has_protector'],
                    is_signed=variant['is_signed'],
                    has_bent_hook=variant['has_bent_hook'],
                    has_cracked_blister=variant['has_cracked_blister'],
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
    is_sealed = forms.TypedChoiceField(
        required=False,
        choices=(('', 'Bez zmian'), ('true', 'Tak'), ('false', 'Nie')),
        coerce=lambda value: {'true': True, 'false': False}.get(value, ''),
        label='Sealed',
    )
    has_soft_corners = forms.TypedChoiceField(
        required=False,
        choices=(('', 'Bez zmian'), ('true', 'Tak'), ('false', 'Nie')),
        coerce=lambda value: {'true': True, 'false': False}.get(value, ''),
        label='Soft corners',
    )
    has_protector = forms.TypedChoiceField(
        required=False,
        choices=(('', 'Bez zmian'), ('true', 'Tak'), ('false', 'Nie')),
        coerce=lambda value: {'true': True, 'false': False}.get(value, ''),
        label='Protector',
    )
    is_signed = forms.TypedChoiceField(
        required=False,
        choices=(('', 'Bez zmian'), ('true', 'Tak'), ('false', 'Nie')),
        coerce=lambda value: {'true': True, 'false': False}.get(value, ''),
        label='Signed',
    )
    has_bent_hook = forms.TypedChoiceField(
        required=False,
        choices=(('', 'Bez zmian'), ('true', 'Tak'), ('false', 'Nie')),
        coerce=lambda value: {'true': True, 'false': False}.get(value, ''),
        label='Bent hook',
    )
    has_cracked_blister = forms.TypedChoiceField(
        required=False,
        choices=(('', 'Bez zmian'), ('true', 'Tak'), ('false', 'Nie')),
        coerce=lambda value: {'true': True, 'false': False}.get(value, ''),
        label='Cracked blister',
    )

    def __init__(self, *args, **kwargs):
        collection = kwargs.pop('collection')
        super().__init__(*args, **kwargs)
        self.collection = collection

    def clean(self):
        cleaned_data = super().clean()
        changed_fields = (
            'condition',
            'packaging_state',
            'is_sealed',
            'has_soft_corners',
            'has_protector',
            'is_signed',
            'has_bent_hook',
            'has_cracked_blister',
        )
        has_quantity_change = cleaned_data.get('quantity') is not None
        has_other_change = any(cleaned_data.get(field_name) != '' for field_name in changed_fields)
        if not (has_quantity_change or has_other_change):
            raise forms.ValidationError('Wybierz przynajmniej jedną zmianę do zastosowania.')
        return cleaned_data

    def apply(self, items):
        updated_count = 0
        for item in items.select_related('model'):
            new_quantity = self.cleaned_data.get('quantity') or item.quantity
            new_condition = self.cleaned_data.get('condition') or item.condition
            new_packaging = self.cleaned_data.get('packaging_state') or item.packaging_state
            new_is_sealed = item.is_sealed if self.cleaned_data.get('is_sealed', '') == '' else self.cleaned_data['is_sealed']
            new_has_soft_corners = item.has_soft_corners if self.cleaned_data.get('has_soft_corners', '') == '' else self.cleaned_data['has_soft_corners']
            new_has_protector = item.has_protector if self.cleaned_data.get('has_protector', '') == '' else self.cleaned_data['has_protector']
            new_is_signed = item.is_signed if self.cleaned_data.get('is_signed', '') == '' else self.cleaned_data['is_signed']
            new_has_bent_hook = item.has_bent_hook if self.cleaned_data.get('has_bent_hook', '') == '' else self.cleaned_data['has_bent_hook']
            new_has_cracked_blister = item.has_cracked_blister if self.cleaned_data.get('has_cracked_blister', '') == '' else self.cleaned_data['has_cracked_blister']
            if new_packaging == 'loose':
                new_is_sealed = False
                new_has_soft_corners = False
                new_has_protector = False
                new_is_signed = False
                new_has_bent_hook = False
                new_has_cracked_blister = False

            if new_packaging not in item.model.available_packaging_states:
                continue

            duplicate_exists = CollectionItem.objects.filter(
                collection=self.collection,
                model=item.model,
                packaging_state=new_packaging,
                condition=new_condition,
                is_sealed=new_is_sealed,
                has_soft_corners=new_has_soft_corners,
                has_protector=new_has_protector,
                is_signed=new_is_signed,
                has_bent_hook=new_has_bent_hook,
                has_cracked_blister=new_has_cracked_blister,
            ).exclude(pk=item.pk).exists()
            if duplicate_exists:
                continue

            if (
                new_quantity != item.quantity
                or new_condition != item.condition
                or new_packaging != item.packaging_state
                or new_is_sealed != item.is_sealed
                or new_has_soft_corners != item.has_soft_corners
                or new_has_protector != item.has_protector
                or new_is_signed != item.is_signed
                or new_has_bent_hook != item.has_bent_hook
                or new_has_cracked_blister != item.has_cracked_blister
            ):
                item.quantity = new_quantity
                item.condition = new_condition
                item.packaging_state = new_packaging
                item.is_sealed = new_is_sealed
                item.has_soft_corners = new_has_soft_corners
                item.has_protector = new_has_protector
                item.is_signed = new_is_signed
                item.has_bent_hook = new_has_bent_hook
                item.has_cracked_blister = new_has_cracked_blister
                item.save(
                    update_fields=[
                        'quantity',
                        'condition',
                        'packaging_state',
                        'is_sealed',
                        'has_soft_corners',
                        'has_protector',
                        'is_signed',
                        'has_bent_hook',
                        'has_cracked_blister',
                    ]
                )
                updated_count += 1

        return updated_count
