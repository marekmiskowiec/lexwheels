import csv
import json
from itertools import groupby
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic.edit import FormView
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django.db.models import Count, F, Q, Sum

from catalog.models import HotWheelsModel

from .forms import (
    CatalogQuickAddForm,
    CollectionBatchAddForm,
    CollectionBulkEditForm,
    CollectionForm,
    CollectionItemForm,
    CollectionItemMultiVariantForm,
)
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


def collection_filter_session_key(collection_id):
    return f'collection_filters_{collection_id}'


ATTRIBUTE_FILTER_FIELDS = (
    ('sealed', 'is_sealed'),
    ('soft_corners', 'has_soft_corners'),
    ('protector', 'has_protector'),
    ('signed', 'is_signed'),
    ('bent_hook', 'has_bent_hook'),
    ('cracked_blister', 'has_cracked_blister'),
)


def parse_boolean_filter(raw_value):
    value = (raw_value or '').strip().lower()
    if value == 'yes':
        return True
    if value == 'no':
        return False
    return None


def build_collection_stats_context(items_queryset):
    packaging_labels = dict(CollectionItem.PACKAGING_CHOICES)
    condition_labels = dict(CollectionItem.CONDITION_CHOICES)
    stats = items_queryset.aggregate(
        total_quantity=Sum('quantity'),
        favorite_count=Count('id', filter=Q(is_favorite=True)),
        variant_count=Count('id'),
        item_count=Count('model_id', distinct=True),
    )
    charts = {
        'brands': build_chart_rows(
            items_queryset.values(label=F('model__brand')).annotate(value=Sum('quantity')).order_by('-value', 'label')[:6]
        ),
        'years': build_chart_rows(
            items_queryset.values(label=F('model__year')).annotate(value=Sum('quantity')).order_by('-value', 'label')[:6]
        ),
        'categories': build_chart_rows(
            items_queryset.values(label=F('model__category')).annotate(value=Sum('quantity')).order_by('-value', 'label')[:6]
        ),
        'packaging': build_chart_rows(
            items_queryset.values(label=F('packaging_state')).annotate(value=Sum('quantity')).order_by('-value', 'label'),
            label_map=packaging_labels,
        ),
        'conditions': build_chart_rows(
            items_queryset.values(label=F('condition')).annotate(value=Sum('quantity')).order_by('-value', 'label'),
            label_map=condition_labels,
        ),
    }
    return {
        'stats': {
            'item_count': stats['item_count'] or 0,
            'variant_count': stats['variant_count'] or 0,
            'total_quantity': stats['total_quantity'] or 0,
            'favorite_count': stats['favorite_count'] or 0,
        },
        'charts': charts,
    }


def build_completion_context(items_queryset, catalog_queryset=None):
    catalog_queryset = catalog_queryset or HotWheelsModel.objects.all()
    owned_model_ids = list(items_queryset.values_list('model_id', flat=True).distinct())
    owned_model_count = len(owned_model_ids)
    total_model_count = catalog_queryset.count()
    completion_percent = int((owned_model_count / total_model_count) * 100) if total_model_count else 0

    owned_by_year = {
        row['model__year']: row['owned']
        for row in items_queryset.exclude(model__year__isnull=True)
        .values('model__year')
        .annotate(owned=Count('model_id', distinct=True))
    }
    total_by_year = {
        row['year']: row['total']
        for row in catalog_queryset.exclude(year__isnull=True)
        .values('year')
        .annotate(total=Count('id'))
    }
    year_rows = []
    for year in sorted(total_by_year):
        total = total_by_year[year]
        owned = owned_by_year.get(year, 0)
        year_rows.append(
            {
                'label': str(year),
                'owned': owned,
                'total': total,
                'percent': int((owned / total) * 100) if total else 0,
            }
        )

    owned_by_category = {
        row['model__category']: row['owned']
        for row in items_queryset.exclude(model__category='')
        .values('model__category')
        .annotate(owned=Count('model_id', distinct=True))
    }
    total_by_category = {
        row['category']: row['total']
        for row in catalog_queryset.exclude(category='')
        .values('category')
        .annotate(total=Count('id'))
    }
    category_rows = []
    for category, total in sorted(total_by_category.items(), key=lambda item: (-item[1], item[0])):
        owned = owned_by_category.get(category, 0)
        category_rows.append(
            {
                'label': category,
                'owned': owned,
                'total': total,
                'percent': int((owned / total) * 100) if total else 0,
            }
        )

    owned_by_series = {
        row['model__series']: row['owned']
        for row in items_queryset.exclude(model__series='')
        .values('model__series')
        .annotate(owned=Count('model_id', distinct=True))
    }
    total_by_series = {
        row['series']: row['total']
        for row in catalog_queryset.exclude(series='')
        .values('series')
        .annotate(total=Count('id'))
    }
    series_rows = []
    for series, owned in owned_by_series.items():
        total = total_by_series.get(series, 0)
        if not total:
            continue
        series_rows.append(
            {
                'label': series,
                'owned': owned,
                'total': total,
                'missing': max(total - owned, 0),
                'percent': int((owned / total) * 100) if total else 0,
            }
        )
    series_rows.sort(key=lambda row: (-row['owned'], -row['percent'], row['label']))

    return {
        'completion': {
            'owned_models': owned_model_count,
            'total_models': total_model_count,
            'percent': completion_percent,
        },
        'completion_by_year': year_rows,
        'completion_by_category': category_rows[:8],
        'completion_by_series': series_rows[:12],
    }


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

        context['owned_collections'] = owned
        context['wishlist_collections'] = wishlist
        stats_context = build_collection_stats_context(owner_items)
        context['stats'] = {
            'collection_count': len(owned),
            'wishlist_count': len(wishlist),
            'item_count': stats_context['stats']['item_count'],
            'variant_count': stats_context['stats']['variant_count'],
            'total_quantity': stats_context['stats']['total_quantity'],
            'favorite_count': stats_context['stats']['favorite_count'],
        }
        return context


class CollectionStatsView(LoginRequiredMixin, ListView):
    template_name = 'collections/stats.html'
    context_object_name = 'collections'

    def get_queryset(self):
        return Collection.objects.filter(owner=self.request.user).prefetch_related('items')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope = self.request.GET.get('scope', '').strip()
        collections = context['collections']
        selected_collection_id = self.request.GET.get('collection', '').strip()
        selected_kind = self.request.GET.get('kind', '').strip()

        items = CollectionItem.objects.filter(collection__owner=self.request.user)
        if selected_collection_id.isdigit():
            items = items.filter(collection_id=int(selected_collection_id))
            scope = 'collection'
        elif selected_kind in {Collection.KIND_OWNED, Collection.KIND_WISHLIST}:
            items = items.filter(collection__kind=selected_kind)
            scope = selected_kind
        elif scope == 'owned':
            items = items.filter(collection__kind=Collection.KIND_OWNED)
        elif scope == 'wishlist':
            items = items.filter(collection__kind=Collection.KIND_WISHLIST)
        else:
            scope = 'all'

        stats_context = build_collection_stats_context(items)
        completion_context = build_completion_context(items)
        context.update(stats_context)
        context.update(completion_context)
        context['selected_scope'] = scope
        context['selected_collection_id'] = selected_collection_id
        context['selected_kind'] = selected_kind
        context['collection_options'] = collections.order_by('kind', 'name')
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

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        base_url = self.object.get_absolute_url()
        session_key = collection_filter_session_key(self.object.pk)

        if request.GET.get('save_filters') == '1':
            filters = {
                key: request.GET.get(key, '').strip()
                for key in (
                    'q',
                    'brand',
                    'condition',
                    'packaging',
                    'sealed',
                    'soft_corners',
                    'protector',
                    'signed',
                    'bent_hook',
                    'cracked_blister',
                )
                if request.GET.get(key, '').strip()
            }
            request.session[session_key] = filters
            messages.success(request, 'Zapisano filtry tej kolekcji.')
            if filters:
                return redirect(f'{base_url}?{urlencode(filters)}')
            return redirect(base_url)

        if request.GET.get('apply_saved_filters') == '1':
            saved_filters = request.session.get(session_key, {})
            if saved_filters:
                return redirect(f'{base_url}?{urlencode(saved_filters)}')
            messages.info(request, 'Brak zapisanych filtrów dla tej kolekcji.')
            return redirect(base_url)

        if request.GET.get('clear_saved_filters') == '1':
            request.session.pop(session_key, None)
            messages.success(request, 'Usunięto zapisane filtry tej kolekcji.')
            return redirect(base_url)

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = self.object.items.select_related('model')
        query = self.request.GET.get('q', '').strip()
        selected_brand = self.request.GET.get('brand', '').strip()
        selected_condition = self.request.GET.get('condition', '').strip()
        selected_packaging = self.request.GET.get('packaging', '').strip()
        selected_sealed = self.request.GET.get('sealed', '').strip()
        selected_soft_corners = self.request.GET.get('soft_corners', '').strip()
        selected_protector = self.request.GET.get('protector', '').strip()
        selected_signed = self.request.GET.get('signed', '').strip()
        selected_bent_hook = self.request.GET.get('bent_hook', '').strip()
        selected_cracked_blister = self.request.GET.get('cracked_blister', '').strip()

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
        for query_key, model_field in ATTRIBUTE_FILTER_FIELDS:
            parsed_value = parse_boolean_filter(self.request.GET.get(query_key, ''))
            if parsed_value is not None:
                items = items.filter(**{model_field: parsed_value})

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

        stats_context = build_collection_stats_context(self.object.items.all())
        context['stats'] = stats_context['stats']
        context['items'] = grouped_items
        context['query'] = query
        context['selected_brand'] = selected_brand
        context['selected_condition'] = selected_condition
        context['selected_packaging'] = selected_packaging
        context['selected_sealed'] = selected_sealed
        context['selected_soft_corners'] = selected_soft_corners
        context['selected_protector'] = selected_protector
        context['selected_signed'] = selected_signed
        context['selected_bent_hook'] = selected_bent_hook
        context['selected_cracked_blister'] = selected_cracked_blister
        context['brand_options'] = (
            self.object.items.exclude(model__brand='')
            .values_list('model__brand', flat=True)
            .distinct()
            .order_by('model__brand')
        )
        context['condition_options'] = CollectionItem.CONDITION_CHOICES
        context['packaging_options'] = CollectionItem.PACKAGING_CHOICES
        context['boolean_filter_options'] = (
            ('', 'Wszystkie'),
            ('yes', 'Tak'),
            ('no', 'Nie'),
        )
        context['filtered_count'] = len(grouped_items)
        context['saved_filters'] = self.request.session.get(collection_filter_session_key(self.object.pk), {})
        context['bulk_edit_form'] = CollectionBulkEditForm(collection=self.object)
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
                'Sealed',
                'Soft Corners',
                'Protector',
                'Signed',
                'Bent Hook',
                'Cracked Blister',
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
                    item.is_sealed,
                    item.has_soft_corners,
                    item.has_protector,
                    item.is_signed,
                    item.has_bent_hook,
                    item.has_cracked_blister,
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
                        'is_sealed': item.is_sealed,
                        'has_soft_corners': item.has_soft_corners,
                        'has_protector': item.has_protector,
                        'is_signed': item.is_signed,
                        'has_bent_hook': item.has_bent_hook,
                        'has_cracked_blister': item.has_cracked_blister,
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


class CollectionBatchEditView(LoginRequiredMixin, View):
    def post(self, request, pk):
        collection = get_object_or_404(Collection, pk=pk, owner=request.user)
        selected_variant_ids = {int(item_id) for item_id in request.POST.getlist('item_ids') if item_id.isdigit()}
        form = CollectionBulkEditForm(request.POST, collection=collection)

        if not selected_variant_ids:
            messages.error(request, 'Zaznacz co najmniej jeden wariant do masowej edycji.')
            return redirect(collection.get_absolute_url())

        if not form.is_valid():
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
            return redirect(collection.get_absolute_url())

        queryset = collection.items.filter(pk__in=selected_variant_ids)
        updated_count = form.apply(queryset)
        skipped_count = len(selected_variant_ids) - updated_count

        if updated_count:
            messages.success(request, f'Zaktualizowano {updated_count} wariantów w kolekcji "{collection.name}".')
        if skipped_count:
            messages.info(request, f'Pominięto {skipped_count} wariantów z powodu duplikatów lub braku zmian.')
        return redirect(collection.get_absolute_url())


class CollectionItemCreateView(LoginRequiredMixin, FormView):
    form_class = CollectionItemMultiVariantForm
    template_name = 'collections/item_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.collection = get_object_or_404(Collection, pk=self.kwargs['collection_pk'], owner=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        selected_model_id = ''
        model_query = self.request.GET.get('q', '').strip()
        if self.request.method == 'POST':
            selected_model_id = self.request.POST.get('model', '').strip()
            model_query = self.request.POST.get('_model_query', '').strip()
        else:
            selected_model_id = self.request.GET.get('model', '').strip()
        kwargs['collection'] = self.collection
        kwargs['model_query'] = model_query
        kwargs['selected_model_id'] = selected_model_id
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
        context['model_query'] = self.request.GET.get('q', '').strip() or self.request.POST.get('_model_query', '').strip()
        context['model_results_count'] = context['form'].fields['model'].queryset.count()
        return context


class CatalogQuickAddView(LoginRequiredMixin, FormView):
    form_class = CatalogQuickAddForm
    template_name = 'catalog/model_list.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['owner'] = self.request.user
        return kwargs

    def form_valid(self, form):
        created_items = form.save()
        collection = form.cleaned_data['collection']
        if len(created_items) == 1:
            messages.success(self.request, f'Dodano 1 wariant do kolekcji "{collection.name}".')
        else:
            messages.success(self.request, f'Dodano {len(created_items)} warianty do kolekcji "{collection.name}".')
        return redirect(form.cleaned_data.get('next') or reverse('catalog:model-list'))

    def form_invalid(self, form):
        for errors in form.errors.values():
            for error in errors:
                messages.error(self.request, error)
        return redirect(form.data.get('next') or reverse('catalog:model-list'))


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
