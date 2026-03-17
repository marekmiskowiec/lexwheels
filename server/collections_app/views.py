from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from catalog.models import HotWheelsModel

from .forms import CollectionForm, CollectionItemForm
from .models import Collection, CollectionItem


class DashboardView(LoginRequiredMixin, ListView):
    template_name = 'collections/dashboard.html'
    context_object_name = 'collections'

    def get_queryset(self):
        return Collection.objects.filter(owner=self.request.user)


class CollectionCreateView(LoginRequiredMixin, CreateView):
    model = Collection
    form_class = CollectionForm
    template_name = 'collections/collection_form.html'

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

class CollectionDetailView(DetailView):
    model = Collection
    template_name = 'collections/collection_detail.html'
    context_object_name = 'collection_obj'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.is_public or (self.request.user.is_authenticated and obj.owner == self.request.user):
            return obj
        raise Http404


class OwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        obj = self.get_object()
        if isinstance(obj, Collection):
            return obj.owner == self.request.user
        return obj.collection.owner == self.request.user


class CollectionUpdateView(OwnerRequiredMixin, UpdateView):
    model = Collection
    form_class = CollectionForm
    template_name = 'collections/collection_form.html'


class CollectionDeleteView(OwnerRequiredMixin, DeleteView):
    model = Collection
    template_name = 'collections/collection_confirm_delete.html'
    success_url = reverse_lazy('collections:dashboard')


class CollectionItemCreateView(LoginRequiredMixin, CreateView):
    model = CollectionItem
    form_class = CollectionItemForm
    template_name = 'collections/item_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.collection = get_object_or_404(Collection, pk=self.kwargs['collection_pk'], owner=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['model'].queryset = HotWheelsModel.objects.all()
        initial_model = self.request.GET.get('model')
        if initial_model and initial_model.isdigit():
            form.initial['model'] = initial_model
        return form

    def form_valid(self, form):
        if self.collection.items.filter(model=form.cleaned_data['model']).exists():
            form.add_error('model', 'Ten model jest już w tej kolekcji.')
            return self.form_invalid(form)
        form.instance.collection = self.collection
        return super().form_valid(form)

    def get_success_url(self):
        return self.collection.get_absolute_url()


class CollectionItemUpdateView(OwnerRequiredMixin, UpdateView):
    model = CollectionItem
    form_class = CollectionItemForm
    template_name = 'collections/item_form.html'

    def get_success_url(self):
        return self.object.collection.get_absolute_url()


class CollectionItemDeleteView(OwnerRequiredMixin, DeleteView):
    model = CollectionItem
    template_name = 'collections/item_confirm_delete.html'

    def get_success_url(self):
        return self.object.collection.get_absolute_url()
