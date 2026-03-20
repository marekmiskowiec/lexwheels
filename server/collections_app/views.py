import csv
import json
import io
import uuid
from itertools import groupby
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic.edit import FormView
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView
from django.db.models import Count, F, Q, Sum

from accounts.models import User
from catalog.models import HotWheelsModel

from .forms import (
    CatalogQuickAddForm,
    CollectionBatchAddForm,
    CollectionBulkEditForm,
    CollectionForm,
    CollectionImportForm,
    CollectionItemForm,
    CollectionItemMultiVariantForm,
)
from .models import Collection, CollectionItem
from .models import ImportBacklogEntry, ImportBacklogReport


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
COLLECTION_IMPORT_SESSION_KEY = 'collection_import_preview'
IMPORT_COLUMN_ALIASES = {
    'toy': {'toy', 'toy id', 'toy_id', 'sku', 'id katalogowy', 'item code'},
    'model_name': {'name', 'model', 'model name', 'nazwa'},
    'year': {'year', 'rok'},
    'category': {'type', 'category', 'kategoria', 'line'},
    'series': {'series', 'seria'},
    'series_number': {'series number', 'series_number', 'nr serii'},
    'quantity': {'amount', 'quantity', 'qty', 'ilosc', 'ilość'},
    'price': {'price', 'cena'},
    'location': {'where', 'location', 'storage', 'miejsce'},
    'color': {'color', 'colour', 'kolor'},
}
IMPORT_CATEGORY_MAP = {
    'half-premium': 'Semi Premium',
    'half premium': 'Semi Premium',
    'semi-premium': 'Semi Premium',
    'semi premium': 'Semi Premium',
    'premium': 'Premium',
    'mainline': 'Mainline',
    'rlc': 'RLC',
    'collectors': 'Collectors',
    'xl': 'XL',
}


def parse_boolean_filter(raw_value):
    value = (raw_value or '').strip().lower()
    if value == 'yes':
        return True
    if value == 'no':
        return False
    return None


def normalize_import_header(value):
    return ' '.join((value or '').strip().lower().replace('_', ' ').split())


def detect_import_columns(headers):
    mapping = {}
    normalized_headers = {normalize_import_header(header): header for header in headers if header}
    for target, aliases in IMPORT_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized_headers:
                mapping[target] = normalized_headers[alias]
                break
    return mapping


def normalize_import_category(value):
    raw = ' '.join((value or '').strip().split())
    if not raw:
        return ''
    return IMPORT_CATEGORY_MAP.get(raw.lower(), raw)


def parse_import_quantity(value):
    raw = (value or '').strip()
    if not raw:
        return 1
    try:
        parsed = int(raw)
    except ValueError:
        return 1
    return max(parsed, 1)


def preferred_packaging_for_model(model):
    for packaging_state in ('short_card', 'long_card', 'loose'):
        if packaging_state in model.available_packaging_states:
            return packaging_state
    return model.available_packaging_states[0] if model.available_packaging_states else 'loose'


def build_import_notes(row_data, include_price=True, include_location=True, include_color=False):
    notes = []
    if include_price and row_data.get('price'):
        notes.append(f"Imported price: {row_data['price']}")
    if include_location and row_data.get('location'):
        notes.append(f"Imported location: {row_data['location']}")
    if include_color and row_data.get('color'):
        notes.append(f"Imported color: {row_data['color']}")
    return '\n'.join(notes)


def record_import_backlog(owner, collection, row_data):
    entry_defaults = {
        'status': ImportBacklogEntry.STATUS_OPEN,
        'report_count': 0,
    }
    entry, created = ImportBacklogEntry.objects.get_or_create(
        toy=row_data.get('toy', ''),
        model_name=row_data.get('model_name', '') or 'Unknown model',
        year=row_data.get('year'),
        category=row_data.get('category', ''),
        series=row_data.get('series', ''),
        series_number=row_data.get('series_number', ''),
        defaults=entry_defaults,
    )
    if entry.status == ImportBacklogEntry.STATUS_RESOLVED and entry.resolved_model_id:
        entry.status = ImportBacklogEntry.STATUS_OPEN
        entry.resolved_model = None
    report, report_created = ImportBacklogReport.objects.get_or_create(
        backlog_entry=entry,
        owner=owner,
        collection=collection,
        color=row_data.get('color', ''),
        defaults={
            'price': row_data.get('price', ''),
            'location': row_data.get('location', ''),
            'source_payload': row_data,
        },
    )
    if report_created:
        entry.report_count += 1
    else:
        report.price = row_data.get('price', '') or report.price
        report.location = row_data.get('location', '') or report.location
        report.source_payload = row_data
        report.import_count += 1
        report.save(update_fields=['price', 'location', 'source_payload', 'import_count', 'last_seen_at'])

    entry.save(
        update_fields=['status', 'resolved_model', 'report_count', 'last_seen_at']
    )
    return entry


def match_import_row(row_data):
    toy = (row_data.get('toy') or '').strip()
    model_name = (row_data.get('model_name') or '').strip()
    year = row_data.get('year')
    category = (row_data.get('category') or '').strip()
    series = (row_data.get('series') or '').strip()
    series_number = (row_data.get('series_number') or '').strip()

    if toy:
        exact_by_toy = HotWheelsModel.objects.filter(toy__iexact=toy).order_by('year', 'number', 'model_name')
        if exact_by_toy.count() == 1:
            return {'status': 'matched', 'model': exact_by_toy.first(), 'reason': 'Toy ID'}
        if exact_by_toy.count() > 1:
            return {'status': 'ambiguous', 'model': None, 'reason': f'Wiele modeli z Toy ID "{toy}"'}

    if not model_name:
        return {'status': 'unmatched', 'model': None, 'reason': 'Brak nazwy modelu'}

    exact_match = HotWheelsModel.objects.filter(model_name__iexact=model_name)
    if year:
        exact_match = exact_match.filter(year=year)
    if category:
        exact_match = exact_match.filter(category__iexact=category)
    if series:
        exact_match = exact_match.filter(series__iexact=series)
    if series_number:
        exact_match = exact_match.filter(series_number__iexact=series_number)
    exact_match = exact_match.order_by('year', 'number', 'model_name')
    if exact_match.count() == 1:
        return {'status': 'matched', 'model': exact_match.first(), 'reason': 'Name + Year + Category + Series'}
    if exact_match.count() > 1:
        return {'status': 'ambiguous', 'model': None, 'reason': 'Wiele modeli pasuje dokładnie'}

    fallback_match = HotWheelsModel.objects.filter(model_name__iexact=model_name)
    if year:
        fallback_match = fallback_match.filter(year=year)
    if series:
        fallback_match = fallback_match.filter(series__iexact=series)
    fallback_match = fallback_match.order_by('year', 'number', 'model_name')
    if fallback_match.count() == 1:
        return {'status': 'matched', 'model': fallback_match.first(), 'reason': 'Name + Year + Series'}
    if fallback_match.count() > 1:
        return {'status': 'ambiguous', 'model': None, 'reason': 'Kilka modeli pasuje po nazwie i serii'}

    relaxed_match = HotWheelsModel.objects.filter(model_name__iexact=model_name)
    if year:
        relaxed_match = relaxed_match.filter(year=year)
    relaxed_match = relaxed_match.order_by('year', 'number', 'model_name')
    if relaxed_match.count() == 1:
        return {'status': 'matched', 'model': relaxed_match.first(), 'reason': 'Name + Year'}
    if relaxed_match.count() > 1:
        return {'status': 'ambiguous', 'model': None, 'reason': 'Kilka modeli pasuje po nazwie'}

    return {'status': 'unmatched', 'model': None, 'reason': 'Nie znaleziono modelu'}


def parse_import_file(uploaded_file):
    decoded = uploaded_file.read().decode('utf-8-sig', errors='replace')
    sample = decoded[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = '\t' if '\t' in sample else ','
    reader = csv.DictReader(io.StringIO(decoded), delimiter=delimiter)
    rows = list(reader)
    return reader.fieldnames or [], rows


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
    def get(self, request, *args, **kwargs):
        query = {'view': 'collections'}
        kind = request.GET.get('kind', '').strip()
        if kind in {Collection.KIND_OWNED, Collection.KIND_WISHLIST}:
            query['kind'] = kind
        return redirect(f"{reverse('collections:community')}?{urlencode(query)}")


class CommunityView(TemplateView):
    template_name = 'collections/community.html'
    paginate_by = 24

    def get_selected_view(self):
        selected_view = self.request.GET.get('view', '').strip()
        if selected_view in {'collections', 'collectors'}:
            return selected_view
        return 'collections'

    def get_selected_kind(self):
        selected_kind = self.request.GET.get('kind', '').strip()
        if selected_kind in {Collection.KIND_OWNED, Collection.KIND_WISHLIST}:
            return selected_kind
        return ''

    def get_collections_queryset(self):
        queryset = Collection.objects.filter(visibility=Collection.VISIBILITY_PUBLIC).select_related('owner')
        selected_kind = self.get_selected_kind()
        if selected_kind:
            queryset = queryset.filter(kind=selected_kind)
        return queryset.order_by('owner__display_name', 'name')

    def get_collectors_queryset(self):
        return (
            User.objects.filter(collections__visibility=Collection.VISIBILITY_PUBLIC)
            .distinct()
            .order_by('display_name', 'email')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_view = self.get_selected_view()
        selected_kind = self.get_selected_kind()
        collections = self.get_collections_queryset()
        collectors = self.get_collectors_queryset()
        active_queryset = collectors if selected_view == 'collectors' else collections

        paginator = Paginator(active_queryset, self.paginate_by)
        page_obj = paginator.get_page(self.request.GET.get('page'))

        context.update(
            {
                'selected_view': selected_view,
                'selected_kind': selected_kind,
                'collections': page_obj.object_list if selected_view == 'collections' else [],
                'collectors': page_obj.object_list if selected_view == 'collectors' else [],
                'page_obj': page_obj,
                'paginator': paginator,
                'is_paginated': page_obj.has_other_pages(),
                'community_counts': {
                    'collections': collections.count(),
                    'collectors': collectors.count(),
                },
            }
        )
        return context


class CollectionCreateView(LoginRequiredMixin, CreateView):
    model = Collection
    form_class = CollectionForm
    template_name = 'collections/collection_form.html'

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class CollectionImportView(LoginRequiredMixin, FormView):
    template_name = 'collections/import.html'
    form_class = CollectionImportForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['owner'] = self.request.user
        return kwargs

    def get_preview(self):
        token = self.request.GET.get('preview') or self.request.POST.get('preview_token')
        previews = self.request.session.get(COLLECTION_IMPORT_SESSION_KEY, {})
        if not token:
            return None
        return previews.get(token)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['preview'] = self.get_preview()
        context['preview_token'] = self.request.GET.get('preview', '').strip()
        return context

    def form_valid(self, form):
        headers, rows = parse_import_file(self.request.FILES['source_file'])
        column_map = detect_import_columns(headers)
        preview_rows = []
        matched_count = 0
        ambiguous_count = 0
        unmatched_count = 0

        for index, row in enumerate(rows, start=1):
            row_data = {
                'toy': (row.get(column_map.get('toy', ''), '') or '').strip(),
                'model_name': (row.get(column_map.get('model_name', ''), '') or '').strip(),
                'year': int((row.get(column_map.get('year', ''), '') or 0)) if (row.get(column_map.get('year', ''), '') or '').strip().isdigit() else None,
                'category': normalize_import_category(row.get(column_map.get('category', ''), '')),
                'series': (row.get(column_map.get('series', ''), '') or '').strip(),
                'series_number': (row.get(column_map.get('series_number', ''), '') or '').strip(),
                'quantity': parse_import_quantity(row.get(column_map.get('quantity', ''), '')),
                'price': (row.get(column_map.get('price', ''), '') or '').strip(),
                'location': (row.get(column_map.get('location', ''), '') or '').strip(),
                'color': (row.get(column_map.get('color', ''), '') or '').strip(),
            }
            match = match_import_row(row_data)
            packaging_state = preferred_packaging_for_model(match['model']) if match['model'] else ''
            preview_row = {
                'row_number': index,
                'source': row_data,
                'status': match['status'],
                'reason': match['reason'],
                'packaging_state': packaging_state,
                'model_id': match['model'].pk if match['model'] else None,
                'model_label': (
                    f"{match['model'].model_name} | {match['model'].year or '-'} | {match['model'].series or '-'} | Toy: {match['model'].toy}"
                    if match['model']
                    else ''
                ),
            }
            preview_rows.append(preview_row)
            if match['status'] == 'matched':
                matched_count += 1
            elif match['status'] == 'ambiguous':
                ambiguous_count += 1
            else:
                unmatched_count += 1
                record_import_backlog(
                    self.request.user,
                    form.cleaned_data.get('collection'),
                    row_data,
                )

        preview_token = uuid.uuid4().hex
        previews = self.request.session.get(COLLECTION_IMPORT_SESSION_KEY, {})
        previews[preview_token] = {
            'column_map': column_map,
            'rows': preview_rows,
            'target_collection_id': form.cleaned_data['collection'].pk if form.cleaned_data['collection'] else None,
            'new_collection_name': (form.cleaned_data.get('new_collection_name') or '').strip(),
            'new_collection_kind': form.cleaned_data['new_collection_kind'],
            'new_collection_visibility': form.cleaned_data['new_collection_visibility'],
            'default_condition': form.cleaned_data['default_condition'],
            'import_mode': form.cleaned_data['import_mode'],
            'append_price_to_notes': form.cleaned_data['append_price_to_notes'],
            'append_location_to_notes': form.cleaned_data['append_location_to_notes'],
            'append_color_to_notes': form.cleaned_data['append_color_to_notes'],
            'summary': {
                'headers': headers,
                'total_rows': len(preview_rows),
                'matched_rows': matched_count,
                'ambiguous_rows': ambiguous_count,
                'unmatched_rows': unmatched_count,
            },
        }
        self.request.session[COLLECTION_IMPORT_SESSION_KEY] = previews
        self.request.session.modified = True
        messages.success(self.request, f'Wczytano plik. Dopasowano {matched_count} z {len(preview_rows)} wierszy.')
        return redirect(f"{reverse('collections:collection-import')}?preview={preview_token}")


class ImportBacklogListView(LoginRequiredMixin, ListView):
    model = ImportBacklogEntry
    template_name = 'collections/import_backlog.html'
    context_object_name = 'entries'
    paginate_by = 50

    def get_queryset(self):
        status = self.request.GET.get('status', '').strip()
        queryset = (
            ImportBacklogEntry.objects.filter(reports__owner=self.request.user)
            .select_related('resolved_model')
            .prefetch_related('reports__collection', 'reports__owner')
            .distinct()
        )
        if status in {ImportBacklogEntry.STATUS_OPEN, ImportBacklogEntry.STATUS_RESOLVED, ImportBacklogEntry.STATUS_IGNORED}:
            queryset = queryset.filter(status=status)
        return queryset.order_by('status', '-last_seen_at', 'model_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_status'] = self.request.GET.get('status', '').strip()
        context['status_options'] = ImportBacklogEntry.STATUS_CHOICES
        context['backlog_stats'] = {
            'open_count': ImportBacklogEntry.objects.filter(reports__owner=self.request.user, status=ImportBacklogEntry.STATUS_OPEN).distinct().count(),
            'resolved_count': ImportBacklogEntry.objects.filter(reports__owner=self.request.user, status=ImportBacklogEntry.STATUS_RESOLVED).distinct().count(),
            'ignored_count': ImportBacklogEntry.objects.filter(reports__owner=self.request.user, status=ImportBacklogEntry.STATUS_IGNORED).distinct().count(),
        }
        return context


class CollectionImportConfirmView(LoginRequiredMixin, View):
    def post(self, request):
        preview_token = request.POST.get('preview_token', '').strip()
        previews = request.session.get(COLLECTION_IMPORT_SESSION_KEY, {})
        preview = previews.get(preview_token)
        if not preview:
            messages.error(request, 'Podgląd importu wygasł. Wczytaj plik ponownie.')
            return redirect(reverse('collections:collection-import'))

        target_collection = None
        if preview.get('target_collection_id'):
            target_collection = get_object_or_404(Collection, pk=preview['target_collection_id'], owner=request.user)
        else:
            target_collection, _ = Collection.objects.get_or_create(
                owner=request.user,
                name=preview['new_collection_name'],
                defaults={
                    'kind': preview['new_collection_kind'],
                    'visibility': preview['new_collection_visibility'],
                },
            )

        imported_count = 0
        updated_count = 0
        skipped_count = 0
        import_mode = preview.get('import_mode', CollectionImportForm.IMPORT_MODE_MERGE)
        for row in preview['rows']:
            if row['status'] != 'matched' or not row['model_id']:
                skipped_count += 1
                continue

            model = get_object_or_404(HotWheelsModel, pk=row['model_id'])
            packaging_state = row['packaging_state'] or preferred_packaging_for_model(model)
            notes = build_import_notes(
                row['source'],
                include_price=preview['append_price_to_notes'],
                include_location=preview['append_location_to_notes'],
                include_color=preview['append_color_to_notes'],
            )
            item = CollectionItem.objects.filter(
                collection=target_collection,
                model=model,
                packaging_state=packaging_state,
                condition=preview['default_condition'],
                is_sealed=False,
                has_soft_corners=False,
                has_protector=False,
                is_signed=False,
                has_bent_hook=False,
                has_cracked_blister=False,
            ).first()

            if item is None:
                CollectionItem.objects.create(
                    collection=target_collection,
                    model=model,
                    packaging_state=packaging_state,
                    condition=preview['default_condition'],
                    is_sealed=False,
                    has_soft_corners=False,
                    has_protector=False,
                    is_signed=False,
                    has_bent_hook=False,
                    has_cracked_blister=False,
                    quantity=row['source']['quantity'],
                    notes=notes,
                )
                imported_count += 1
                continue

            if import_mode == CollectionImportForm.IMPORT_MODE_SKIP:
                skipped_count += 1
                continue

            if import_mode == CollectionImportForm.IMPORT_MODE_REPLACE:
                item.quantity = row['source']['quantity']
                if notes:
                    item.notes = notes
                item.save(update_fields=['quantity', 'notes'])
                updated_count += 1
                continue

            if import_mode == CollectionImportForm.IMPORT_MODE_MERGE:
                item.quantity += row['source']['quantity']
                if notes:
                    item.notes = '\n'.join(filter(None, [item.notes, notes]))
                item.save(update_fields=['quantity', 'notes'])
                updated_count += 1

        previews.pop(preview_token, None)
        request.session[COLLECTION_IMPORT_SESSION_KEY] = previews
        request.session.modified = True
        messages.success(
            request,
            f'Import zakończony. Dodano {imported_count} pozycji, zaktualizowano {updated_count}, pominięto {skipped_count}.',
        )
        return redirect(target_collection.get_absolute_url())

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
