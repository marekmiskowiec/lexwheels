from django import forms


class CatalogImageImportForm(forms.Form):
    packaging_state = forms.ChoiceField(label='Wariant zdjęcia')
    source_url = forms.URLField(label='Link do zdjęcia', max_length=1000)

    def __init__(self, *args, model_obj=None, **kwargs):
        super().__init__(*args, **kwargs)
        packaging_choices = [('generic', 'Ogólne / nieprzypisane')]
        if model_obj is not None:
            packaging_choices.extend(model_obj.available_packaging_choices)
        self.fields['packaging_state'].choices = packaging_choices
