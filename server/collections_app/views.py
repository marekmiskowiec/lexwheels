import csv
import json
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic.edit import FormView
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django.db.models import Count, F, Q, Sum

from catalog.models import HotWheelsModel

from .forms import CollectionBatchAddForm, CollectionForm, CollectionItemForm, CollectionItemMultiVariantForm
from .models import Collection, CollectionItem


def build_chart_rows(rows, label_map=None):
    rows = list(rows)
    max_value = max((row['value'] for row in rows), default=0)
    chart_rows = []
    for row in rows:
        raw_label = row['label']
        percent = int((row['value'] / max_value) * 100) if max_value else 0
        chart_rows.append(
            {
                'label': (label_map or {}).get(raw_label, raw_label) or '-',
                'value': row['value'],
                'percent': percent,
            }
        )
    return chart_rows


class DashboardView(LoginRequiredMixin, ListView):
    template_name = 'collections/dashboard.html'
    context_object_name = 'collections'

    def get_queryset(self):
        return Collection.objects.filter(owner=self.request.user).prefetch_related('items')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        owner_items = CollectionItem.objects.filter(collection__owner=self.request.user)
        owned = []
        wishlist = []
        for collection in context['collections']:
            if collection.is_wishlist:
                wishlist.append(collection)
            else:
                owned.append(collection)

        stats = owner_items.aggregate(
            total_quantity=Sum('quantity'),
            favorite_count=Count('id', filter=Q(is_favorite=True)),
        )
        context['owned_collections'] = owned
        context['wishlist_collections'] = wishlist
        packaging_labels = dict(CollectionItem.PACKAGING_CHOICES)
        condition_labels = dict(CollectionItem.CONDITION_CHOICES)
        context['stats'] = {
            'collection_count': len(owned),
            'wishlist_count': len(wishlist),
            'item_count': owner_items.values('model_id').distinct().count(),
            'variant_count': owner_items.count(),
            'total_quantity': stats['total_quantity'] or 0,
            'favorite_count': stats['favorite_count'] or 0,
        }
        context['charts'] = {
            'brands': build_chart_rows(
                owner_items.values(label=F('model__brand')).annotate(value=Sum('quantity')).order_by('-value', 'label')[:6]
            ),
            'years': build_chart_rows(
                owner_items.values(label=F('model__year')).annotate(value=Sum('quantity')).order_by('-value', 'label')[:6]
            ),
            'categories': build_chart_rows(
                owner_items.values(label=F('model__category')).annotate(value=Sum('quantity')).order_by('-value', 'label')[:6]
            ),
            'packaging': build_chart_rows(
                owner_items.values(label=F('packaging_state')).annotate(value=Sum('quantity')).order_by('-value', 'label'),
                label_map=packaging_labels,
            ),
            'conditions': build_chart_rows(
                owner_items.values(label=F('condition')).annotate(value=Sum('quantity')).order_by('-value', 'label'),
                label_map=condition_labels,
            ),
        }
        return context


class PublicCollectionListView(ListView):
    model = Collection
    template_name = 'collections/public_collection_list.html'
    context_object_name = 'collections'
    paginate_by = 24

    def get_queryset(self):
        kind = self.request.GET.get('kind', '').strip()
        queryset = Collection.objects.filter(visibility=Collection.VISIBILITY_PUBLIC).select_related('owner')
        if kind in {Collection.KIND_OWNED, Collection.KIND_WISHLIST}:
            queryset = queryset.filter(kind=kind)
        return queryset.order_by('owner__display_name', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_kind'] = self.request.GET.get('kind', '').strip()
        return context


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = self.object.items.select_related('model')
        query = self.request.GET.get('q', '').strip()
        selected_brand = self.request.GET.get('brand', '').strip()
        selected_condition = self.request.GET.get('condition', '').strip()
        selected_packaging = self.request.GET.get('packaging', '').strip()

        if query:
            items = items.filter(
                Q(model__model_name__icontains=query)
                | Q(model__toy__icontains=query)
                | Q(model__number__icontains=query)
                | Q(model__brand__icontains=query)
                | Q(model__series__icontains=query)
            )
        if selected_brand:
            items = items.filter(model__brand=selected_brand)
        if selected_condition in dict(CollectionItem.CONDITION_CHOICES):
            items = items.filter(condition=selected_condition)
        if selected_packaging in dict(CollectionItem.PACKAGING_CHOICES):
            items = items.filter(packaging_state=selected_packaging)

        grouped_items = []
        ordered_items = list(items.order_by('model__number', 'model__model_name', 'packaging_state', 'condition', 'pk'))
        for model_id, group in groupby(ordered_items, key=lambda item: item.model_id):
            variants = list(group)
            grouped_items.append(
                {
                    'model': variants[0].model,
                    'variants': variants,
                    'total_quantity': sum(item.quantity for item in variants),
                    'favorite_count': sum(1 for item in variants if item.is_favorite),
                }
            )

        packaging_labels = dict(CollectionItem.PACKAGING_CHOICES)
        condition_labels = dict(CollectionItem.CONDITION_CHOICES)
        context['stats'] = {
            'item_count': self.object.items.values('model_id').distinct().count(),
            'variant_count': self.object.items.count(),
            'total_quantity': sum(item.quantity for item in self.object.items.all()),
            'favorite_count': sum(1 for item in self.object.items.all() if item.is_favorite),
        }
        context['charts'] = {
            'brands': build_chart_rows(
                self.object.items.values(label=F('model__brand')).annotate(value=Sum('quantity')).order_by('-value', 'label')[:6]
            ),
            'years': build_chart_rows(
                self.object.items.values(label=F('model__year')).annotate(value=Sum('quantity')).order_by('-value', 'label')[:6]
            ),
            'categories': build_chart_rows(
                self.object.items.values(label=F('model__category')).annotate(value=Sum('quantity')).order_by('-value', 'label')[:6]
            ),
            'packaging': build_chart_rows(
                self.object.items.values(label=F('packaging_state')).annotate(value=Sum('quantity')).order_by('-value', 'label'),
                label_map=packaging_labels,
            ),
            'conditions': build_chart_rows(
                self.object.items.values(label=F('condition')).annotate(value=Sum('quantity')).order_by('-value', 'label'),
                label_map=condition_labels,
            ),
        }
        context['items'] = grouped_items
        context['query'] = query
        context['selected_brand'] = selected_brand
        context['selected_condition'] = selected_condition
        context['selected_packaging'] = selected_packaging
        context['brand_options'] = (
            self.object.items.exclude(model__brand='')
            .values_list('model__brand', flat=True)
            .distinct()
            .order_by('model__brand')
        )
        context['condition_options'] = CollectionItem.CONDITION_CHOICES
        context['packaging_options'] = CollectionItem.PACKAGING_CHOICES
        context['filtered_count'] = len(grouped_items)
        return context


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


class CollectionExportView(LoginRequiredMixin, View):
    def get(self, request, pk, fmt):
        collection = get_object_or_404(Collection, pk=pk, owner=request.user)
        items = collection.items.select_related('model').all()

        if fmt == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{collection.name.lower().replace(" ", "_")}.csv"'
            writer = csv.writer(response)
            writer.writerow([
                'Toy',
                'Number',
                'Model Name',
                'Series',
                'Series Number',
                'Quantity',
                'Condition',
                'Packaging State',
                'Acquired At',
                'Is Favorite',
                'Notes',
            ])
            for item in items:
                writer.writerow([
                    item.model.toy,
                    item.model.number,
                    item.model.model_name,
                    item.model.series,
                    item.model.series_number,
                    item.quantity,
                    item.condition,
                    item.packaging_state,
                    item.acquired_at.isoformat() if item.acquired_at else '',
                    item.is_favorite,
                    item.notes,
                ])
            return response

        if fmt == 'json':
            payload = {
                'collection': {
                    'name': collection.name,
                    'description': collection.description,
                    'kind': collection.kind,
                    'visibility': collection.visibility,
                },
                'items': [
                    {
                        'toy': item.model.toy,
                        'number': item.model.number,
                        'model_name': item.model.model_name,
                        'series': item.model.series,
                        'series_number': item.model.series_number,
                        'quantity': item.quantity,
                        'condition': item.condition,
                        'packaging_state': item.packaging_state,
                        'acquired_at': item.acquired_at.isoformat() if item.acquired_at else None,
                        'is_favorite': item.is_favorite,
                        'notes': item.notes,
                    }
                    for item in items
                ],
            }
            response = HttpResponse(
                json.dumps(payload, ensure_ascii=False, indent=2),
                content_type='application/json',
            )
            response['Content-Disposition'] = f'attachment; filename="{collection.name.lower().replace(" ", "_")}.json"'
            return response

        raise Http404


class CollectionBatchAddView(LoginRequiredMixin, View):
    def post(self, request):
        form = CollectionBatchAddForm(request.POST, owner=request.user)
        selected_ids = [int(model_id) for model_id in request.POST.getlist('model_ids') if model_id.isdigit()]
        next_url = request.POST.get('next') or reverse_lazy('catalog:model-list')

        if not form.is_valid():
            messages.error(request, 'Wybierz kolekcję docelową.')
            return redirect(next_url)

        if not selected_ids:
            messages.error(request, 'Nie zaznaczono żadnych modeli.')
            return redirect(next_url)

        collection = form.cleaned_data['collection']
        existing_model_ids = set(collection.items.filter(model_id__in=selected_ids).values_list('model_id', flat=True))
        added_count = 0

        for model in HotWheelsModel.objects.filter(pk__in=selected_ids):
            if model.pk in existing_model_ids:
                continue
            CollectionItem.objects.create(collection=collection, model=model)
            added_count += 1

        skipped_count = len(selected_ids) - added_count
        if added_count:
            messages.success(request, f'Dodano {added_count} modeli do kolekcji "{collection.name}".')
        if skipped_count:
            messages.info(request, f'Pominięto {skipped_count} modeli, które były już w tej kolekcji.')
        return redirect(next_url)


class CollectionBatchDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        collection = get_object_or_404(Collection, pk=pk, owner=request.user)
        selected_variant_ids = {int(item_id) for item_id in request.POST.getlist('item_ids') if item_id.isdigit()}
        selected_model_ids = {int(model_id) for model_id in request.POST.getlist('model_ids') if model_id.isdigit()}

        queryset = collection.items.all()
        if selected_model_ids:
            queryset = queryset.filter(Q(pk__in=selected_variant_ids) | Q(model_id__in=selected_model_ids))
        else:
            queryset = queryset.filter(pk__in=selected_variant_ids)

        deleted_variants = queryset.count()
        deleted_models = queryset.values('model_id').distinct().count()

        if not deleted_variants:
            messages.error(request, 'Nie zaznaczono żadnych modeli ani wariantów do usunięcia.')
            return redirect(collection.get_absolute_url())

        queryset.delete()
        if deleted_models and deleted_variants:
            messages.success(
                request,
                f'Usunięto {deleted_variants} wariantów dla {deleted_models} modeli z kolekcji "{collection.name}".',
            )
        return redirect(collection.get_absolute_url())


class CollectionItemCreateView(LoginRequiredMixin, FormView):
    form_class = CollectionItemMultiVariantForm
    template_name = 'collections/item_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.collection = get_object_or_404(Collection, pk=self.kwargs['collection_pk'], owner=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['collection'] = self.collection
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        initial_model = self.request.GET.get('model')
        if initial_model and initial_model.isdigit():
            initial['model'] = initial_model
        return initial

    def form_valid(self, form):
        created_items = form.save()
        if len(created_items) == 1:
            messages.success(self.request, 'Dodano 1 wariant modelu do kolekcji.')
        else:
            messages.success(self.request, f'Dodano {len(created_items)} warianty modelu do kolekcji.')
        return super().form_valid(form)

    def get_success_url(self):
        return self.collection.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_multi_variant_form'] = True
        context['collection_obj'] = self.collection
        return context


class CollectionItemUpdateView(OwnerRequiredMixin, UpdateView):
    model = CollectionItem
    form_class = CollectionItemForm
    template_name = 'collections/item_form.html'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.collection = self.object.collection
        return form

    def get_success_url(self):
        return self.object.collection.get_absolute_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_multi_variant_form'] = False
        context['collection_obj'] = self.object.collection
        return context


class CollectionItemDeleteView(OwnerRequiredMixin, DeleteView):
    model = CollectionItem
    template_name = 'collections/item_confirm_delete.html'

    def get_success_url(self):
        return self.object.collection.get_absolute_url()
