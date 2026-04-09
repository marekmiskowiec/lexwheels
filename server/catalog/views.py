import json
import shlex
from pathlib import Path
from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from collections_app.forms import CollectionBatchAddForm
from collections_app.models import Collection, CollectionItem, WantedItem

from .models import HotWheelsModel


CATALOG_FILTER_SESSION_KEY = 'catalog_filters'
CATALOG_SCOPE_PROFILE = 'profile'
CATALOG_SCOPE_ALL = 'all'
CASE_METADATA_ROOT = settings.PROJECT_ROOT / 'data' / 'case-highlights' / 'hot-wheels' / 'mainline'
IMAGE_WORKFLOW_ALLOWED_FIELDS = (
    'brand',
    'toy',
    'number',
    'model_name',
    'year',
    'category',
    'series',
    'exclusive_store',
    'photo_url',
    'local_photo_path',
    'short_card_photo_url',
    'short_card_local_photo_path',
    'long_card_photo_url',
    'long_card_local_photo_path',
    'loose_photo_url',
    'loose_local_photo_path',
    'images_verified_at',
    'images_verified_by',
)
IMAGE_WORKFLOW_SORT_OPTIONS = (
    ('workflow', 'Domyślnie'),
    ('newest', 'Najnowszy rok'),
    ('oldest', 'Najstarszy rok'),
    ('name', 'Nazwa A-Z'),
    ('number', 'Numer / Toy'),
)
IMAGE_WORKFLOW_NAMES = {'missing', 'unassigned', 'assigned', 'complete'}
IMAGE_WORKFLOW_PAGE_SIZE = 100


class CatalogScopeMixin:
    def get_scope_mode(self) -> str:
        requested_scope = self.request.GET.get('scope', '').strip().lower()
        if requested_scope in {CATALOG_SCOPE_ALL, CATALOG_SCOPE_PROFILE}:
            return requested_scope
        if self.request.user.is_authenticated and self.request.user.catalog_scope_enabled:
            return CATALOG_SCOPE_PROFILE
        return CATALOG_SCOPE_ALL

    def apply_profile_scope(self, queryset):
        if self.get_scope_mode() != CATALOG_SCOPE_PROFILE:
            return queryset
        if not self.request.user.is_authenticated:
            return queryset
        return self.request.user.apply_catalog_scope(queryset)


class ModelListView(CatalogScopeMixin, ListView):
    model = HotWheelsModel
    template_name = 'catalog/model_list.html'
    context_object_name = 'models'
    paginate_by = 36
    table_page_size_options = (25, 50, 100)
    sort_options = {
        'number': ('number', 'model_name'),
        '-number': ('-number', '-model_name'),
        'year': ('year', 'number', 'model_name'),
        '-year': ('-year', '-number', 'model_name'),
        'category': ('category', 'year', 'number', 'model_name'),
        '-category': ('-category', '-year', 'number', 'model_name'),
        'exclusive': ('exclusive_store', 'special_tag', 'year', 'number', 'model_name'),
        '-exclusive': ('-exclusive_store', '-special_tag', '-year', 'number', 'model_name'),
        'name': ('model_name',),
        '-name': ('-model_name',),
        'series': ('series', 'series_number', 'year', 'number', 'model_name'),
        '-series': ('-series', '-series_number', '-year', 'number', 'model_name'),
        'toy': ('toy', 'number', 'model_name'),
        '-toy': ('-toy', 'number', 'model_name'),
        'case': ('case_codes', 'year', 'number', 'model_name'),
        '-case': ('-case_codes', '-year', 'number', 'model_name'),
    }
    case_mix_disabled_categories = frozenset({'premium', 'semi premium', 'rlc', 'xl', '5 pack'})

    def get(self, request, *args, **kwargs):
        base_url = request.path
        if request.GET.get('save_filters') == '1':
            filters = {
                key: request.GET.get(key, '').strip()
                for key in (
                    'q', 'brand', 'series', 'year', 'category', 'exclusive_store', 'special_tag', 'case_code', 'sort', 'scope', 'only_unowned'
                )
                if request.GET.get(key, '').strip()
            }
            request.session[CATALOG_FILTER_SESSION_KEY] = filters
            messages.success(request, 'Zapisano filtry katalogu.')
            if filters:
                return redirect(f'{base_url}?{urlencode(filters)}')
            return redirect(base_url)

        if request.GET.get('apply_saved_filters') == '1':
            saved_filters = request.session.get(CATALOG_FILTER_SESSION_KEY, {})
            if saved_filters:
                return redirect(f'{base_url}?{urlencode(saved_filters)}')
            messages.info(request, 'Brak zapisanych filtrów katalogu.')
            return redirect(base_url)

        if request.GET.get('clear_saved_filters') == '1':
            request.session.pop(CATALOG_FILTER_SESSION_KEY, None)
            messages.success(request, 'Usunięto zapisane filtry katalogu.')
            return redirect(base_url)

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = self.build_catalog_queryset()
        sort = self.get_selected_filters()['sort']
        return queryset.order_by(*self.sort_options.get(sort, self.sort_options['number']))

    def get_paginate_by(self, queryset):
        selected_filters = self.get_selected_filters()
        if selected_filters['view'] != 'table':
            return self.paginate_by

        per_page = self.request.GET.get('per_page', '').strip()
        if per_page.isdigit() and int(per_page) in self.table_page_size_options:
            return int(per_page)
        return self.table_page_size_options[0]

    def get_selected_filters(self) -> dict[str, str]:
        raw_query = self.request.GET.get('q', '').strip()
        parsed_query = self.parse_search_query(raw_query)
        selected_view = self.request.GET.get('view', 'table').strip().lower() or 'table'
        if selected_view not in {'grid', 'table'}:
            selected_view = 'table'
        per_page = self.request.GET.get('per_page', '').strip()
        if not (per_page.isdigit() and int(per_page) in self.table_page_size_options):
            per_page = str(self.table_page_size_options[0])
        selected_sort = self.request.GET.get('sort', 'number').strip() or 'number'
        if selected_sort not in self.sort_options:
            selected_sort = 'number'
        selected_category = self.request.GET.get('category', '').strip() or parsed_query['category']
        selected_case_code = self.normalize_case_code(
            self.request.GET.get('case_code', '').strip() or parsed_query['case_code']
        )
        if not self.category_supports_case_mix(selected_category):
            selected_case_code = ''
        selected_only_unowned = self.request.GET.get('only_unowned', '').strip() if self.request.user.is_authenticated else ''
        return {
            'raw_query': raw_query,
            'query': parsed_query['text'],
            'series': self.request.GET.get('series', '').strip() or parsed_query['series'],
            'brand': self.request.GET.get('brand', '').strip() or parsed_query['brand'],
            'year': self.request.GET.get('year', '').strip() or parsed_query['year'],
            'category': selected_category,
            'exclusive_store': self.request.GET.get('exclusive_store', '').strip() or parsed_query['exclusive_store'],
            'special_tag': self.request.GET.get('special_tag', '').strip() or parsed_query['special_tag'],
            'case_code': selected_case_code,
            'sort': selected_sort,
            'view': selected_view,
            'per_page': per_page,
            'only_unowned': '1' if selected_only_unowned == '1' else '',
            'exclusive_store_from_query': bool(
                parsed_query['exclusive_store'] and not self.request.GET.get('exclusive_store', '').strip()
            ),
            'special_tag_from_query': bool(
                parsed_query['special_tag'] and not self.request.GET.get('special_tag', '').strip()
            ),
        }

    def build_catalog_queryset(self, *, exclude_filters: set[str] | None = None):
        queryset = self.apply_profile_scope(HotWheelsModel.objects.all())
        filters = self.get_selected_filters()
        exclude_filters = exclude_filters or set()

        if filters['query'] and 'query' not in exclude_filters:
            queryset = queryset.filter(
                Q(toy__icontains=filters['query'])
                | Q(number__icontains=filters['query'])
                | Q(model_name__icontains=filters['query'])
                | Q(brand__icontains=filters['query'])
                | Q(series__icontains=filters['query'])
            )
        if filters['brand'] and 'brand' not in exclude_filters:
            queryset = queryset.filter(brand=filters['brand'])
        if filters['series'] and 'series' not in exclude_filters:
            queryset = queryset.filter(series=filters['series'])
        if filters['year'].isdigit() and 'year' not in exclude_filters:
            queryset = queryset.filter(year=int(filters['year']))
        if filters['category'] and 'category' not in exclude_filters:
            queryset = queryset.filter(category=filters['category'])
        if filters['exclusive_store'] and 'exclusive_store' not in exclude_filters:
            if filters.get('exclusive_store_from_query'):
                queryset = queryset.filter(exclusive_store__icontains=filters['exclusive_store'])
            else:
                queryset = queryset.filter(exclusive_store=filters['exclusive_store'])
        if filters['special_tag'] and 'special_tag' not in exclude_filters:
            if filters.get('special_tag_from_query'):
                queryset = queryset.filter(special_tag__icontains=filters['special_tag'])
            else:
                queryset = queryset.filter(special_tag=filters['special_tag'])
        if filters['case_code'] and 'case_code' not in exclude_filters:
            queryset = queryset.filter(self.build_case_filter(filters['case_code']))
        if filters['only_unowned'] and 'only_unowned' not in exclude_filters and self.request.user.is_authenticated:
            owned_model_ids = CollectionItem.objects.filter(
                collection__owner=self.request.user,
                collection__kind=Collection.KIND_OWNED,
            ).values('model_id')
            queryset = queryset.exclude(pk__in=owned_model_ids)

        return queryset

    @staticmethod
    def parse_search_query(raw_query: str) -> dict[str, str]:
        parsed = {
            'text': '',
            'year': '',
            'brand': '',
            'category': '',
            'series': '',
            'exclusive_store': '',
            'special_tag': '',
            'case_code': '',
        }
        if not raw_query:
            return parsed

        try:
            tokens = shlex.split(raw_query)
        except ValueError:
            tokens = raw_query.split()

        free_text_tokens = []
        for token in tokens:
            if ':' not in token:
                free_text_tokens.append(token)
                continue
            key, value = token.split(':', 1)
            normalized_key = key.strip().lower()
            normalized_value = value.strip()
            if not normalized_value:
                free_text_tokens.append(token)
                continue
            if normalized_key in {'y', 'year'} and normalized_value.isdigit():
                parsed['year'] = normalized_value
            elif normalized_key in {'b', 'brand'}:
                parsed['brand'] = normalized_value
            elif normalized_key in {'c', 'cat', 'category'}:
                parsed['category'] = normalized_value
            elif normalized_key in {'s', 'series'}:
                parsed['series'] = normalized_value
            elif normalized_key in {'x', 'ex', 'exclusive'}:
                parsed['exclusive_store'] = normalized_value
            elif normalized_key in {'t', 'tag'}:
                parsed['special_tag'] = normalized_value
            elif normalized_key in {'k', 'case', 'mix'}:
                parsed['case_code'] = normalized_value
            else:
                free_text_tokens.append(token)

        parsed['text'] = ' '.join(free_text_tokens).strip()
        return parsed

    @staticmethod
    def normalize_case_code(value: str) -> str:
        return ''.join(char for char in value.strip().upper() if char.isalnum())

    @classmethod
    def category_supports_case_mix(cls, category: str) -> bool:
        normalized = (category or '').strip().lower()
        if not normalized:
            return True
        return normalized not in cls.case_mix_disabled_categories

    @classmethod
    def build_case_filter(cls, case_code: str) -> Q:
        normalized = cls.normalize_case_code(case_code)
        if not normalized:
            return Q()
        return (
            Q(case_codes=normalized)
            | Q(case_codes__startswith=f'{normalized},')
            | Q(case_codes__endswith=f',{normalized}')
            | Q(case_codes__contains=f',{normalized},')
        )

    @staticmethod
    def extract_case_code_options(queryset) -> list[str]:
        case_codes = set()
        for raw_value in queryset.exclude(case_codes='').values_list('case_codes', flat=True):
            for code in str(raw_value).split(','):
                normalized = code.strip().upper()
                if normalized:
                    case_codes.add(normalized)
        return sorted(case_codes)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        model_list = list(context['models'])
        context['models'] = model_list
        if context.get('page_obj') is not None:
            context['page_obj'].object_list = model_list
        filtered_count = context['page_obj'].paginator.count if context.get('page_obj') else len(context['models'])
        total_queryset = HotWheelsModel.objects.all()
        scope_mode = self.get_scope_mode()
        scoped_total_queryset = self.apply_profile_scope(HotWheelsModel.objects.all())
        selected_filters = self.get_selected_filters()
        context['query'] = selected_filters['raw_query']
        context['selected_scope'] = scope_mode
        context['selected_brand'] = selected_filters['brand']
        context['selected_series'] = selected_filters['series']
        context['selected_year'] = selected_filters['year']
        context['selected_category'] = selected_filters['category']
        context['selected_exclusive_store'] = selected_filters['exclusive_store']
        context['selected_special_tag'] = selected_filters['special_tag']
        context['selected_case_code'] = selected_filters['case_code']
        context['category_supports_case_mix'] = self.category_supports_case_mix(selected_filters['category'])
        context['selected_sort'] = selected_filters['sort']
        context['selected_sort_base'] = selected_filters['sort'].lstrip('-')
        context['selected_view'] = selected_filters['view']
        context['selected_per_page'] = selected_filters['per_page']
        context['selected_only_unowned'] = selected_filters['only_unowned']
        context['table_page_size_options'] = self.table_page_size_options
        context['current_path'] = self.request.get_full_path()
        series_options_queryset = self.build_catalog_queryset(exclude_filters={'series'})
        brand_options_queryset = self.build_catalog_queryset(exclude_filters={'brand'})
        year_options_queryset = self.build_catalog_queryset(exclude_filters={'year'})
        category_options_queryset = self.build_catalog_queryset(exclude_filters={'category'})
        exclusive_options_queryset = self.build_catalog_queryset(exclude_filters={'exclusive_store'})
        special_tag_options_queryset = self.build_catalog_queryset(exclude_filters={'special_tag'})
        case_code_options_queryset = self.build_catalog_queryset(exclude_filters={'case_code'})
        context['series_options'] = (
            series_options_queryset.exclude(series='')
            .values_list('series', flat=True)
            .distinct()
            .order_by('series')
        )
        context['brand_options'] = (
            brand_options_queryset.exclude(brand='')
            .values_list('brand', flat=True)
            .distinct()
            .order_by('brand')
        )
        context['year_options'] = (
            year_options_queryset.exclude(year__isnull=True)
            .values_list('year', flat=True)
            .distinct()
            .order_by('year')
        )
        context['category_options'] = (
            category_options_queryset.exclude(category='')
            .values_list('category', flat=True)
            .distinct()
            .order_by('category')
        )
        context['exclusive_store_options'] = (
            exclusive_options_queryset.exclude(exclusive_store='')
            .values_list('exclusive_store', flat=True)
            .distinct()
            .order_by('exclusive_store')
        )
        context['special_tag_options'] = (
            special_tag_options_queryset.exclude(special_tag='')
            .values_list('special_tag', flat=True)
            .distinct()
            .order_by('special_tag')
        )
        context['case_code_options'] = (
            self.extract_case_code_options(case_code_options_queryset)
            if context['category_supports_case_mix']
            else []
        )
        stats_queryset = scoped_total_queryset if scope_mode == CATALOG_SCOPE_PROFILE else total_queryset
        context['catalog_stats'] = {
            'total_models': stats_queryset.count(),
            'filtered_models': filtered_count,
            'brand_count': stats_queryset.exclude(brand='').values('brand').distinct().count(),
            'year_count': stats_queryset.exclude(year__isnull=True).values('year').distinct().count(),
            'category_count': stats_queryset.exclude(category='').values('category').distinct().count(),
        }
        context['scope_summary'] = self.request.user.catalog_scope_summary if (
            self.request.user.is_authenticated and scope_mode == CATALOG_SCOPE_PROFILE
        ) else []
        if self.request.user.is_authenticated:
            context['batch_add_form'] = CollectionBatchAddForm(owner=self.request.user, initial={'next': self.request.get_full_path()})
            model_ids = [item.pk for item in model_list]
            owned_rows = CollectionItem.objects.filter(
                collection__owner=self.request.user,
                collection__kind=Collection.KIND_OWNED,
                model_id__in=model_ids,
            ).values('model_id').annotate(
                entry_count=Count('id'),
                total_quantity=Sum('quantity'),
            )
            owned_summary = {
                row['model_id']: {
                    'entry_count': row['entry_count'] or 0,
                    'total_quantity': row['total_quantity'] or 0,
                }
                for row in owned_rows
            }
            for item in model_list:
                item.catalog_collection_summary = owned_summary.get(item.pk, {'entry_count': 0, 'total_quantity': 0})
                item.catalog_is_owned = bool(owned_summary.get(item.pk))
        context['search_suggestions_url'] = reverse('catalog:model-search-suggestions')
        context['saved_filters'] = self.request.session.get(CATALOG_FILTER_SESSION_KEY, {})
        return context


class ModelSearchSuggestionsView(CatalogScopeMixin, View):
    def get(self, request, *args, **kwargs):
        raw_query = request.GET.get('q', '').strip()
        query = ModelListView.parse_search_query(raw_query)['text']
        if len(query) < 2:
            return JsonResponse({'suggestions': []})

        queryset = self.apply_profile_scope(HotWheelsModel.objects.all()).filter(
            Q(model_name__icontains=query)
            | Q(brand__icontains=query)
            | Q(series__icontains=query)
            | Q(toy__icontains=query)
            | Q(number__icontains=query)
        ).order_by('model_name', 'year', 'number')

        suggestions = []
        seen = set()
        for model in queryset.only('model_name', 'toy', 'year')[:12]:
            model_name = model.model_name.strip()
            if not model_name or model_name in seen:
                continue
            seen.add(model_name)
            suggestions.append(
                {
                    'value': model_name,
                    'label': f'{model_name} | {model.toy}{f" | {model.year}" if model.year else ""}',
                }
            )

        return JsonResponse({'suggestions': suggestions})


class ModelDetailView(CatalogScopeMixin, DetailView):
    model = HotWheelsModel
    template_name = 'catalog/model_detail.html'
    context_object_name = 'model_obj'

    def get_workflow_filters(self) -> dict[str, str]:
        return {
            'scope': self.get_scope_mode(),
            'category': self.request.GET.get('category', '').strip(),
            'series': self.request.GET.get('series', '').strip(),
            'year': self.request.GET.get('year', '').strip(),
            'verified': self.request.GET.get('verified', '').strip(),
            'sort': self.request.GET.get('sort', 'workflow').strip() or 'workflow',
        }

    def apply_workflow_filters(self, queryset, filters: dict[str, str]):
        if filters['category']:
            queryset = queryset.filter(category=filters['category'])
        if filters['series']:
            queryset = queryset.filter(series=filters['series'])
        if filters['year'].isdigit():
            queryset = queryset.filter(year=int(filters['year']))
        return queryset

    def workflow_sort_key(self, entry: dict, sort_name: str):
        model = entry['model']
        default_key = (
            model.category or '',
            -(model.year or 0),
            model.number or '',
            model.model_name or '',
        )
        if sort_name == 'oldest':
            return (model.category or '', model.year or 0, model.number or '', model.model_name or '')
        if sort_name == 'name':
            return (model.model_name or '', -(model.year or 0), model.number or '')
        if sort_name == 'number':
            return (model.number or '', model.toy or '', model.model_name or '')
        return default_key

    def sort_workflow_entries(self, entries: list[dict], sort_name: str) -> list[dict]:
        sort_name = sort_name if sort_name in dict(IMAGE_WORKFLOW_SORT_OPTIONS) else 'workflow'
        return sorted(entries, key=lambda entry: self.workflow_sort_key(entry, sort_name))

    def build_detail_url(self, model, workflow: str, filters: dict[str, str]) -> str:
        params = {'workflow': workflow}
        if filters['scope'] == CATALOG_SCOPE_PROFILE:
            params['scope'] = filters['scope']
        if filters['category']:
            params['category'] = filters['category']
        if filters['series']:
            params['series'] = filters['series']
        if filters['year']:
            params['year'] = filters['year']
        if workflow == 'complete' and filters.get('verified') in {'verified', 'unverified'}:
            params['verified'] = filters['verified']
        if filters['sort'] and filters['sort'] != 'workflow':
            params['sort'] = filters['sort']
        return f"{model.get_absolute_url()}?{urlencode(params)}"

    def get_workflow_entries(self, workflow: str, queryset, filters: dict[str, str]) -> list[dict]:
        entries = []
        for model in queryset.only(*IMAGE_WORKFLOW_ALLOWED_FIELDS):
            if workflow == 'missing':
                missing_choices = model.missing_packaging_image_choices
                if not missing_choices:
                    continue
                entries.append({'model': model, 'missing_choices': missing_choices})
            elif workflow == 'unassigned':
                if not model.has_unassigned_image:
                    continue
                entries.append({'model': model})
            elif workflow == 'assigned':
                panels = model.packaging_image_panels
                if not panels:
                    continue
                entries.append({'model': model, 'panels': panels})
            elif workflow == 'complete':
                panels = model.packaging_image_panels
                if not model.has_complete_packaging_images:
                    continue
                if filters.get('verified') == 'verified' and not model.images_verified:
                    continue
                if filters.get('verified') == 'unverified' and model.images_verified:
                    continue
                entries.append({'model': model, 'panels': panels, 'is_verified': model.images_verified})
        return self.sort_workflow_entries(entries, filters['sort'])

    def build_workflow_detail_navigation(self, current_model):
        workflow = self.request.GET.get('workflow', '').strip()
        if workflow not in IMAGE_WORKFLOW_NAMES:
            return None

        filters = self.get_workflow_filters()
        queryset = self.apply_workflow_filters(self.apply_profile_scope(HotWheelsModel.objects.all()), filters)
        entries = self.get_workflow_entries(workflow, queryset, filters)
        model_ids = [entry['model'].pk for entry in entries]
        if current_model.pk not in model_ids:
            return None

        current_index = model_ids.index(current_model.pk)
        previous_entry = entries[current_index - 1] if current_index > 0 else None
        next_entry = entries[current_index + 1] if current_index + 1 < len(entries) else None
        list_url_name = {
            'missing': 'catalog:missing-packaging-images',
            'unassigned': 'catalog:unassigned-images',
            'assigned': 'catalog:assigned-images',
            'complete': 'catalog:complete-images',
        }[workflow]
        params = {}
        if filters['scope'] == CATALOG_SCOPE_PROFILE:
            params['scope'] = filters['scope']
        if filters['category']:
            params['category'] = filters['category']
        if filters['series']:
            params['series'] = filters['series']
        if filters['year']:
            params['year'] = filters['year']
        if workflow == 'complete' and filters['verified'] in {'verified', 'unverified'}:
            params['verified'] = filters['verified']
        if filters['sort'] and filters['sort'] != 'workflow':
            params['sort'] = filters['sort']
        list_url = reverse(list_url_name)
        if params:
            list_url = f'{list_url}?{urlencode(params)}'
        return {
            'workflow': workflow,
            'label': {
                'missing': 'Brakujące warianty zdjęć',
                'unassigned': 'Nieprzypisane zdjęcia',
                'assigned': 'Przypisane zdjęcia',
                'complete': 'Komplet zdjęć',
            }[workflow],
            'index': current_index + 1,
            'total': len(entries),
            'list_url': list_url,
            'previous': {
                'url': self.build_detail_url(previous_entry['model'], workflow, filters),
                'label': previous_entry['model'].model_name,
            } if previous_entry else None,
            'next': {
                'url': self.build_detail_url(next_entry['model'], workflow, filters),
                'label': next_entry['model'].model_name,
            } if next_entry else None,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        model_obj = context['model_obj']
        context['case_entries'] = [
            {
                'code': case_code,
                'label': f'Case {case_code}',
                'url': reverse('catalog:case-mix-detail', args=[model_obj.year, case_code.lower()]) if model_obj.year else '',
            }
            for case_code in model_obj.case_code_list
        ]
        context['related_catalog_links'] = [
            {
                'label': f'Rok {model_obj.year}',
                'url': f"{reverse('catalog:model-list')}?{urlencode({'year': model_obj.year})}",
            }
            for _ in [1]
            if model_obj.year
        ]
        if model_obj.category:
            context['related_catalog_links'].append(
                {
                    'label': model_obj.category,
                    'url': f"{reverse('catalog:model-list')}?{urlencode({'category': model_obj.category})}",
                }
            )
        if model_obj.series:
            context['related_catalog_links'].append(
                {
                    'label': model_obj.series,
                    'url': f"{reverse('catalog:model-list')}?{urlencode({'series': model_obj.series, 'year': model_obj.year})}"
                    if model_obj.year
                    else f"{reverse('catalog:model-list')}?{urlencode({'series': model_obj.series})}",
                }
            )
        if model_obj.brand:
            context['related_catalog_links'].append(
                {
                    'label': model_obj.brand,
                    'url': f"{reverse('catalog:model-list')}?{urlencode({'brand': model_obj.brand})}",
                }
            )
        if model_obj.special_tag:
            context['related_catalog_links'].append(
                {
                    'label': model_obj.special_tag,
                    'url': f"{reverse('catalog:model-list')}?{urlencode({'special_tag': model_obj.special_tag})}",
                }
            )
        if model_obj.exclusive_store:
            context['related_catalog_links'].append(
                {
                    'label': model_obj.exclusive_store,
                    'url': f"{reverse('catalog:model-list')}?{urlencode({'exclusive_store': model_obj.exclusive_store})}",
                }
            )

        if self.request.user.is_authenticated:
            owned_items = list(
                CollectionItem.objects.filter(
                    collection__owner=self.request.user,
                    collection__kind=Collection.KIND_OWNED,
                    model=model_obj,
                ).select_related('collection')
            )
            wanted_items = list(
                WantedItem.objects.filter(
                    owner=self.request.user,
                    model=model_obj,
                )
            )
            context['owned_items'] = owned_items
            context['wanted_items'] = wanted_items
            context['owned_total_quantity'] = sum(item.quantity for item in owned_items)
            context['owned_collection_count'] = len({item.collection_id for item in owned_items})
            context['active_wanted_count'] = sum(1 for item in wanted_items if item.is_active)
        else:
            context['owned_items'] = []
            context['wanted_items'] = []
            context['owned_total_quantity'] = 0
            context['owned_collection_count'] = 0
            context['active_wanted_count'] = 0
        context['image_workflow_nav'] = self.build_workflow_detail_navigation(model_obj)
        return context


class CatalogImageAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return bool(self.request.user.is_staff or self.request.user.is_superuser)


class CatalogAdminDashboardView(CatalogImageAdminRequiredMixin, CatalogScopeMixin, TemplateView):
    template_name = 'catalog/admin_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_mode = self.get_scope_mode()
        queryset = self.apply_profile_scope(HotWheelsModel.objects.all())
        category_rows = (
            queryset.values('category')
            .annotate(model_count=Count('id'), year_count=Count('year', distinct=True))
            .order_by('-model_count', 'category')
        )
        image_quality_fields = (
            'category',
            'exclusive_store',
            'photo_url',
            'local_photo_path',
            'short_card_photo_url',
            'short_card_local_photo_path',
            'long_card_photo_url',
            'long_card_local_photo_path',
            'loose_photo_url',
            'loose_local_photo_path',
        )
        missing_model_count = 0
        unassigned_model_count = 0
        assigned_model_count = 0
        complete_model_count = 0
        verified_model_count = 0
        complete_unverified_model_count = 0
        for model in queryset.only(*image_quality_fields):
            has_assigned = bool(model.packaging_image_panels)
            has_unassigned = model.has_unassigned_image
            has_missing = bool(model.missing_packaging_image_states)
            if has_missing:
                missing_model_count += 1
            if has_unassigned:
                unassigned_model_count += 1
            if has_assigned:
                assigned_model_count += 1
            if model.has_complete_packaging_images:
                complete_model_count += 1
                if model.images_verified:
                    verified_model_count += 1
                else:
                    complete_unverified_model_count += 1

        query_suffix = f'?scope=profile' if scope_mode == CATALOG_SCOPE_PROFILE else ''
        context['selected_scope'] = scope_mode
        context['scope_summary'] = self.request.user.catalog_scope_summary if (
            self.request.user.is_authenticated and scope_mode == CATALOG_SCOPE_PROFILE
        ) else []
        context['admin_stats'] = {
            'model_count': queryset.count(),
            'missing_model_count': missing_model_count,
            'unassigned_model_count': unassigned_model_count,
            'assigned_model_count': assigned_model_count,
            'complete_model_count': complete_model_count,
            'verified_model_count': verified_model_count,
            'complete_unverified_model_count': complete_unverified_model_count,
        }
        context['category_summary'] = [
            {
                'name': (row['category'] or 'Bez kategorii').strip(),
                'model_count': row['model_count'],
                'year_count': row['year_count'],
                'url': f"{reverse('catalog:model-list')}?{urlencode({'scope': scope_mode, 'category': row['category']})}"
                if row['category']
                else f"{reverse('catalog:model-list')}?{urlencode({'scope': scope_mode})}",
            }
            for row in category_rows
        ]
        context['admin_links'] = [
            {
                'title': 'Brakujące warianty zdjęć',
                'meta': 'Modele, którym brakuje co najmniej jednego wariantu zdjęcia.',
                'count': missing_model_count,
                'url': f"{reverse('catalog:missing-packaging-images')}{query_suffix}",
            },
            {
                'title': 'Nieprzypisane zdjęcia',
                'meta': 'Ogólne zdjęcia do ręcznego przypisania jako krótka, długa lub luzak.',
                'count': unassigned_model_count,
                'url': f"{reverse('catalog:unassigned-images')}{query_suffix}",
            },
            {
                'title': 'Przypisane zdjęcia',
                'meta': 'Modele ze zdjęciami wariantów już sklasyfikowanymi w bazie.',
                'count': assigned_model_count,
                'url': f"{reverse('catalog:assigned-images')}{query_suffix}",
            },
            {
                'title': 'Komplet zdjęć',
                'meta': 'Modele z kompletem zdjęć, które czekają jeszcze na potwierdzenie jakości.',
                'count': complete_unverified_model_count,
                'url': f"{reverse('catalog:complete-images')}?{urlencode({'scope': scope_mode, 'verified': 'unverified'})}"
                if scope_mode == CATALOG_SCOPE_PROFILE
                else f"{reverse('catalog:complete-images')}?{urlencode({'verified': 'unverified'})}",
            },
            {
                'title': 'Verified',
                'meta': 'Modele z kompletem zdjęć już ręcznie potwierdzonym przez staff.',
                'count': verified_model_count,
                'url': f"{reverse('catalog:complete-images')}?{urlencode({'scope': scope_mode, 'verified': 'verified'})}"
                if scope_mode == CATALOG_SCOPE_PROFILE
                else f"{reverse('catalog:complete-images')}?{urlencode({'verified': 'verified'})}",
            },
        ]
        return context


class CatalogImageWorkflowMixin(CatalogScopeMixin):
    workflow_name = ''

    @staticmethod
    def packaging_state_empty_q(packaging_state: str) -> Q:
        return Q(**{f'{packaging_state}_photo_url': '', f'{packaging_state}_local_photo_path': ''})

    @staticmethod
    def packaging_state_present_q(packaging_state: str) -> Q:
        return ~CatalogImageWorkflowMixin.packaging_state_empty_q(packaging_state)

    @staticmethod
    def generic_image_present_q() -> Q:
        return ~Q(photo_url='', local_photo_path='')

    def get_workflow_filters(self) -> dict[str, str]:
        return {
            'scope': self.get_scope_mode(),
            'category': self.request.GET.get('category', '').strip(),
            'series': self.request.GET.get('series', '').strip(),
            'year': self.request.GET.get('year', '').strip(),
            'verified': self.request.GET.get('verified', '').strip(),
            'sort': self.request.GET.get('sort', 'workflow').strip() or 'workflow',
        }

    def apply_workflow_filters(self, queryset, filters: dict[str, str]):
        if filters['category']:
            queryset = queryset.filter(category=filters['category'])
        if filters['series']:
            queryset = queryset.filter(series=filters['series'])
        if filters['year'].isdigit():
            queryset = queryset.filter(year=int(filters['year']))
        if self.workflow_name == 'complete':
            if filters.get('verified') == 'verified':
                queryset = queryset.filter(images_verified_at__isnull=False)
            elif filters.get('verified') == 'unverified':
                queryset = queryset.filter(images_verified_at__isnull=True)
        return queryset

    def workflow_sort_key(self, entry: dict, sort_name: str):
        model = entry['model']
        default_key = (
            model.category or '',
            -(model.year or 0),
            model.number or '',
            model.model_name or '',
        )
        if sort_name == 'oldest':
            return (model.category or '', model.year or 0, model.number or '', model.model_name or '')
        if sort_name == 'name':
            return (model.model_name or '', -(model.year or 0), model.number or '')
        if sort_name == 'number':
            return (model.number or '', model.toy or '', model.model_name or '')
        return default_key

    def sort_workflow_entries(self, entries: list[dict], sort_name: str) -> list[dict]:
        sort_name = sort_name if sort_name in dict(IMAGE_WORKFLOW_SORT_OPTIONS) else 'workflow'
        return sorted(entries, key=lambda entry: self.workflow_sort_key(entry, sort_name))

    def workflow_queryset_order(self, sort_name: str) -> tuple[str, ...]:
        if sort_name == 'oldest':
            return ('category', 'year', 'number', 'model_name')
        if sort_name == 'name':
            return ('model_name', '-year', 'number')
        if sort_name == 'number':
            return ('number', 'toy', 'model_name')
        return ('category', '-year', 'number', 'model_name')

    def workflow_relevant_missing_q(self) -> Q:
        short_missing = self.packaging_state_empty_q('short_card')
        long_missing = self.packaging_state_empty_q('long_card')
        loose_missing = self.packaging_state_empty_q('loose')
        excluded_short_q = Q(category__in=['Premium', 'Semi Premium', 'XL', 'RLC', '5 Pack']) | ~Q(exclusive_store='')
        return (
            (excluded_short_q & (long_missing | loose_missing))
            | (~excluded_short_q & (short_missing | long_missing | loose_missing))
        )

    def workflow_entry_queryset(self, queryset, filters: dict[str, str]):
        queryset = self.apply_workflow_filters(queryset, filters)
        relevant_missing_q = self.workflow_relevant_missing_q()
        if self.workflow_name == 'missing':
            queryset = queryset.filter(relevant_missing_q)
        elif self.workflow_name == 'unassigned':
            queryset = queryset.filter(self.generic_image_present_q()).filter(relevant_missing_q)
        elif self.workflow_name == 'assigned':
            short_present = self.packaging_state_present_q('short_card')
            long_present = self.packaging_state_present_q('long_card')
            loose_present = self.packaging_state_present_q('loose')
            excluded_short_q = Q(category__in=['Premium', 'Semi Premium', 'XL', 'RLC', '5 Pack']) | ~Q(exclusive_store='')
            queryset = queryset.filter(
                (excluded_short_q & (long_present | loose_present))
                | (~excluded_short_q & (short_present | long_present | loose_present))
            )
        elif self.workflow_name == 'complete':
            queryset = queryset.exclude(relevant_missing_q)
        return queryset.order_by(*self.workflow_queryset_order(filters['sort']))

    def paginate_workflow_queryset(self, queryset):
        paginator = Paginator(queryset, IMAGE_WORKFLOW_PAGE_SIZE)
        page_number = self.request.GET.get('page') or 1
        return paginator.get_page(page_number)

    def workflow_querystring(self, filters: dict[str, str]) -> str:
        params = {}
        if filters['scope'] == CATALOG_SCOPE_PROFILE:
            params['scope'] = filters['scope']
        if filters['year']:
            params['year'] = filters['year']
        if filters['category']:
            params['category'] = filters['category']
        if filters['series']:
            params['series'] = filters['series']
        if self.workflow_name == 'complete' and filters.get('verified') in {'verified', 'unverified'}:
            params['verified'] = filters['verified']
        if filters['sort'] and filters['sort'] != 'workflow':
            params['sort'] = filters['sort']
        return urlencode(params)

    def build_detail_url(self, model, filters: dict[str, str]) -> str:
        params = {'workflow': self.workflow_name}
        if filters['scope'] == CATALOG_SCOPE_PROFILE:
            params['scope'] = filters['scope']
        if filters['category']:
            params['category'] = filters['category']
        if filters['series']:
            params['series'] = filters['series']
        if filters['year']:
            params['year'] = filters['year']
        if self.workflow_name == 'complete' and filters.get('verified') in {'verified', 'unverified'}:
            params['verified'] = filters['verified']
        if filters['sort'] and filters['sort'] != 'workflow':
            params['sort'] = filters['sort']
        query = urlencode(params)
        return f"{model.get_absolute_url()}?{query}" if query else model.get_absolute_url()

    def workflow_options_context(self, scope_mode: str, base_queryset, filters: dict[str, str]) -> dict:
        category_options = (
            self.apply_profile_scope(HotWheelsModel.objects.all())
            .exclude(category='')
            .values_list('category', flat=True)
            .distinct()
            .order_by('category')
        )
        year_options = (
            self.apply_profile_scope(HotWheelsModel.objects.all())
            .exclude(year__isnull=True)
            .values_list('year', flat=True)
            .distinct()
            .order_by('-year')
        )

        series_queryset = self.apply_profile_scope(HotWheelsModel.objects.all())
        if filters['category']:
            series_queryset = series_queryset.filter(category=filters['category'])
        if filters['year'].isdigit():
            series_queryset = series_queryset.filter(year=int(filters['year']))
        series_options = (
            series_queryset.exclude(series='')
            .values_list('series', flat=True)
            .distinct()
            .order_by('series')
        )
        return {
            'selected_scope': scope_mode,
            'selected_category': filters['category'],
            'selected_series': filters['series'],
            'selected_year': filters['year'],
            'selected_sort': filters['sort'],
            'category_options': category_options,
            'series_options': series_options,
            'year_options': year_options,
            'sort_options': IMAGE_WORKFLOW_SORT_OPTIONS,
        }

    def build_workflow_detail_navigation(self, current_model):
        workflow = self.request.GET.get('workflow', '').strip()
        if workflow not in IMAGE_WORKFLOW_NAMES:
            return None

        filters = self.get_workflow_filters()
        queryset = self.apply_workflow_filters(self.apply_profile_scope(HotWheelsModel.objects.all()), filters)
        entries = self.get_workflow_entries(queryset, filters)
        model_ids = [entry['model'].pk for entry in entries]
        if current_model.pk not in model_ids:
            return None

        current_index = model_ids.index(current_model.pk)
        previous_entry = entries[current_index - 1] if current_index > 0 else None
        next_entry = entries[current_index + 1] if current_index + 1 < len(entries) else None
        list_url_name = {
            'missing': 'catalog:missing-packaging-images',
            'unassigned': 'catalog:unassigned-images',
            'assigned': 'catalog:assigned-images',
            'complete': 'catalog:complete-images',
        }[workflow]
        params = {}
        if filters['scope'] == CATALOG_SCOPE_PROFILE:
            params['scope'] = filters['scope']
        if filters['category']:
            params['category'] = filters['category']
        if filters['series']:
            params['series'] = filters['series']
        if filters['year']:
            params['year'] = filters['year']
        if workflow == 'complete' and filters.get('verified') in {'verified', 'unverified'}:
            params['verified'] = filters['verified']
        if filters['sort'] and filters['sort'] != 'workflow':
            params['sort'] = filters['sort']
        list_url = reverse(list_url_name)
        if params:
            list_url = f'{list_url}?{urlencode(params)}'
        return {
            'workflow': workflow,
            'label': {
                'missing': 'Brakujące warianty zdjęć',
                'unassigned': 'Nieprzypisane zdjęcia',
                'assigned': 'Przypisane zdjęcia',
                'complete': 'Komplet zdjęć',
            }[workflow],
            'index': current_index + 1,
            'total': len(entries),
            'list_url': list_url,
            'previous': {
                'url': self.build_detail_url(previous_entry['model'], filters),
                'label': previous_entry['model'].model_name,
            } if previous_entry else None,
            'next': {
                'url': self.build_detail_url(next_entry['model'], filters),
                'label': next_entry['model'].model_name,
            } if next_entry else None,
        }


class MissingPackagingImageListView(CatalogImageWorkflowMixin, TemplateView):
    template_name = 'catalog/missing_packaging_images.html'
    workflow_name = 'missing'

    def get_workflow_entries(self, queryset, filters: dict[str, str]) -> list[dict]:
        models_with_missing_images = []
        for model in queryset.only(*IMAGE_WORKFLOW_ALLOWED_FIELDS):
            missing_choices = model.missing_packaging_image_choices
            if not missing_choices:
                continue
            models_with_missing_images.append(
                {
                    'model': model,
                    'missing_choices': missing_choices,
                    'primary_image_src': model.catalog_primary_thumb_src or model.catalog_primary_image_src,
                    'detail_url': self.build_detail_url(model, filters),
                }
            )
        return self.sort_workflow_entries(models_with_missing_images, filters['sort'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_mode = self.get_scope_mode()
        filters = self.get_workflow_filters()
        queryset = self.workflow_entry_queryset(self.apply_profile_scope(HotWheelsModel.objects.all()), filters)
        page_obj = self.paginate_workflow_queryset(queryset)
        models_with_missing_images = self.get_workflow_entries(page_obj.object_list, filters)
        context['missing_image_models'] = models_with_missing_images
        context['missing_image_stats'] = {
            'model_count': queryset.count(),
        }
        context.update(self.workflow_options_context(scope_mode, queryset, filters))
        context['page_obj'] = page_obj
        context['paginator'] = page_obj.paginator
        context['is_paginated'] = page_obj.has_other_pages()
        context['workflow_querystring'] = self.workflow_querystring(filters)
        context['scope_summary'] = self.request.user.catalog_scope_summary if (
            self.request.user.is_authenticated and scope_mode == CATALOG_SCOPE_PROFILE
        ) else []
        return context


class UnassignedImageListView(CatalogImageAdminRequiredMixin, CatalogImageWorkflowMixin, TemplateView):
    template_name = 'catalog/unassigned_images.html'
    workflow_name = 'unassigned'

    def get_workflow_entries(self, queryset, filters: dict[str, str]) -> list[dict]:
        unassigned_models = []
        for model in queryset.only(*IMAGE_WORKFLOW_ALLOWED_FIELDS):
            if not model.has_unassigned_image:
                continue
            unassigned_models.append(
                {
                    'model': model,
                    'image_src': model.unassigned_image_src,
                    'detail_url': self.build_detail_url(model, filters),
                }
            )
        return self.sort_workflow_entries(unassigned_models, filters['sort'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_mode = self.get_scope_mode()
        filters = self.get_workflow_filters()
        queryset = self.workflow_entry_queryset(self.apply_profile_scope(HotWheelsModel.objects.all()), filters)
        page_obj = self.paginate_workflow_queryset(queryset)
        unassigned_models = self.get_workflow_entries(page_obj.object_list, filters)
        context['unassigned_models'] = unassigned_models
        context['unassigned_stats'] = {'model_count': queryset.count()}
        context.update(self.workflow_options_context(scope_mode, queryset, filters))
        context['page_obj'] = page_obj
        context['paginator'] = page_obj.paginator
        context['is_paginated'] = page_obj.has_other_pages()
        context['workflow_querystring'] = self.workflow_querystring(filters)
        context['scope_summary'] = self.request.user.catalog_scope_summary if (
            self.request.user.is_authenticated and scope_mode == CATALOG_SCOPE_PROFILE
        ) else []
        return context


class AssignedImageListView(CatalogImageAdminRequiredMixin, CatalogImageWorkflowMixin, TemplateView):
    template_name = 'catalog/assigned_images.html'
    workflow_name = 'assigned'

    def get_workflow_entries(self, queryset, filters: dict[str, str]) -> list[dict]:
        assigned_models = []
        for model in queryset.only(*IMAGE_WORKFLOW_ALLOWED_FIELDS):
            panels = model.packaging_image_panels
            if not panels:
                continue
            assigned_models.append(
                {
                    'model': model,
                    'panels': panels,
                    'primary_image_src': model.catalog_primary_thumb_src or model.catalog_primary_image_src,
                    'detail_url': self.build_detail_url(model, filters),
                }
            )
        return self.sort_workflow_entries(assigned_models, filters['sort'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_mode = self.get_scope_mode()
        filters = self.get_workflow_filters()
        queryset = self.workflow_entry_queryset(self.apply_profile_scope(HotWheelsModel.objects.all()), filters)
        page_obj = self.paginate_workflow_queryset(queryset)
        assigned_models = self.get_workflow_entries(page_obj.object_list, filters)
        context['assigned_models'] = assigned_models
        context['assigned_stats'] = {
            'model_count': queryset.count(),
        }
        context.update(self.workflow_options_context(scope_mode, queryset, filters))
        context['page_obj'] = page_obj
        context['paginator'] = page_obj.paginator
        context['is_paginated'] = page_obj.has_other_pages()
        context['workflow_querystring'] = self.workflow_querystring(filters)
        context['scope_summary'] = self.request.user.catalog_scope_summary if (
            self.request.user.is_authenticated and scope_mode == CATALOG_SCOPE_PROFILE
        ) else []
        return context


class CompleteImageListView(CatalogImageAdminRequiredMixin, CatalogImageWorkflowMixin, TemplateView):
    template_name = 'catalog/complete_images.html'
    workflow_name = 'complete'

    def get_workflow_entries(self, queryset, filters: dict[str, str]) -> list[dict]:
        complete_models = []
        for model in queryset.only(*IMAGE_WORKFLOW_ALLOWED_FIELDS, 'images_verified_at', 'images_verified_by'):
            if not model.has_complete_packaging_images:
                continue
            complete_models.append(
                {
                    'model': model,
                    'panels': model.packaging_image_panels,
                    'primary_image_src': model.catalog_primary_thumb_src or model.catalog_primary_image_src,
                    'detail_url': self.build_detail_url(model, filters),
                    'is_verified': model.images_verified,
                }
            )
        return self.sort_workflow_entries(complete_models, filters['sort'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_mode = self.get_scope_mode()
        filters = self.get_workflow_filters()
        queryset = self.workflow_entry_queryset(self.apply_profile_scope(HotWheelsModel.objects.all()), filters)
        page_obj = self.paginate_workflow_queryset(queryset)
        complete_models = self.get_workflow_entries(page_obj.object_list, filters)
        context['complete_models'] = complete_models
        context['complete_stats'] = {
            'model_count': queryset.count(),
            'verified_model_count': queryset.filter(images_verified_at__isnull=False).count(),
        }
        context.update(self.workflow_options_context(scope_mode, queryset, filters))
        context['page_obj'] = page_obj
        context['paginator'] = page_obj.paginator
        context['is_paginated'] = page_obj.has_other_pages()
        context['workflow_querystring'] = self.workflow_querystring(filters)
        context['scope_summary'] = self.request.user.catalog_scope_summary if (
            self.request.user.is_authenticated and scope_mode == CATALOG_SCOPE_PROFILE
        ) else []
        return context


class ToggleImageVerificationView(CatalogImageAdminRequiredMixin, View):
    def post(self, request, pk):
        model = HotWheelsModel.objects.filter(pk=pk).first()
        if not model:
            raise Http404
        if not model.has_complete_packaging_images:
            messages.error(request, 'Można potwierdzać tylko modele z kompletem zdjęć.')
            return redirect(request.POST.get('next') or model.get_absolute_url())

        if model.images_verified:
            model.images_verified_at = None
            model.images_verified_by = None
            model.save(update_fields=['images_verified_at', 'images_verified_by'])
            messages.success(request, 'Cofnięto potwierdzenie kompletu zdjęć.')
        else:
            model.images_verified_at = timezone.now()
            model.images_verified_by = request.user
            model.save(update_fields=['images_verified_at', 'images_verified_by'])
            messages.success(request, 'Potwierdzono komplet zdjęć.')
        return redirect(request.POST.get('next') or model.get_absolute_url())


class AssignGenericImageView(CatalogImageAdminRequiredMixin, View):
    def post(self, request, pk, packaging_state):
        model = HotWheelsModel.objects.filter(pk=pk).first()
        if not model:
            raise Http404
        if packaging_state not in dict(HotWheelsModel.PACKAGING_LABELS):
            raise Http404
        if packaging_state not in model.available_packaging_states:
            raise Http404
        if not model.has_unassigned_image:
            messages.info(request, 'To zdjęcie zostało już przypisane.')
            return redirect(request.POST.get('next') or reverse('catalog:unassigned-images'))

        reference = model.unassigned_image_reference
        path_attr = f'{packaging_state}_local_photo_path'
        url_attr = f'{packaging_state}_photo_url'
        setattr(model, path_attr, reference['local_path'])
        setattr(model, url_attr, reference['url'])
        model.local_photo_path = ''
        model.photo_url = ''
        model.save(update_fields=[path_attr, url_attr, 'local_photo_path', 'photo_url'])
        messages.success(request, f'Przypisano zdjęcie do wariantu: {model.packaging_labels[packaging_state]}.')
        return redirect(request.POST.get('next') or reverse('catalog:unassigned-images'))


class ReassignPackagingImageView(CatalogImageAdminRequiredMixin, View):
    def post(self, request, pk, source_packaging_state, target_packaging_state):
        model = HotWheelsModel.objects.filter(pk=pk).first()
        if not model:
            raise Http404
        if source_packaging_state not in dict(HotWheelsModel.PACKAGING_LABELS):
            raise Http404
        if source_packaging_state not in model.available_packaging_states:
            raise Http404

        source_reference = model.packaging_image_reference(source_packaging_state)
        if model.image_reference_signature(source_reference) == ('', ''):
            messages.info(request, 'Wybrany wariant nie ma przypisanego zdjęcia.')
            return redirect(request.POST.get('next') or model.get_absolute_url())

        if target_packaging_state == 'unassigned':
            generic_reference = model.generic_image_reference()
            generic_signature = model.image_reference_signature(generic_reference)
            source_signature = model.image_reference_signature(source_reference)
            if generic_signature != ('', '') and generic_signature != source_signature:
                messages.error(
                    request,
                    'Model ma już nieprzypisane zdjęcie. Najpierw przypisz lub popraw istniejące zdjęcie ogólne.',
                )
                return redirect(request.POST.get('next') or model.get_absolute_url())
            model.local_photo_path = source_reference['local_path']
            model.photo_url = source_reference['url']
            setattr(model, f'{source_packaging_state}_local_photo_path', '')
            setattr(model, f'{source_packaging_state}_photo_url', '')
            model.save(update_fields=[
                'local_photo_path',
                'photo_url',
                f'{source_packaging_state}_local_photo_path',
                f'{source_packaging_state}_photo_url',
            ])
            messages.success(request, 'Cofnięto przypisanie zdjęcia do nieprzypisanego.')
            return redirect(request.POST.get('next') or model.get_absolute_url())

        if target_packaging_state not in dict(HotWheelsModel.PACKAGING_LABELS):
            raise Http404
        if target_packaging_state not in model.available_packaging_states:
            raise Http404
        if target_packaging_state == source_packaging_state:
            return redirect(request.POST.get('next') or model.get_absolute_url())

        target_reference = model.packaging_image_reference(target_packaging_state)
        if model.image_reference_signature(target_reference) != ('', ''):
            messages.error(request, f'Wariant {model.packaging_labels[target_packaging_state]} ma już własne zdjęcie.')
            return redirect(request.POST.get('next') or model.get_absolute_url())

        setattr(model, f'{target_packaging_state}_local_photo_path', source_reference['local_path'])
        setattr(model, f'{target_packaging_state}_photo_url', source_reference['url'])
        setattr(model, f'{source_packaging_state}_local_photo_path', '')
        setattr(model, f'{source_packaging_state}_photo_url', '')
        model.save(update_fields=[
            f'{target_packaging_state}_local_photo_path',
            f'{target_packaging_state}_photo_url',
            f'{source_packaging_state}_local_photo_path',
            f'{source_packaging_state}_photo_url',
        ])
        messages.success(
            request,
            f'Przeniesiono zdjęcie z {model.packaging_labels[source_packaging_state]} do {model.packaging_labels[target_packaging_state]}.',
        )
        return redirect(request.POST.get('next') or model.get_absolute_url())


def load_case_year_metadata(year: int) -> dict:
    path = CASE_METADATA_ROOT / f'{year}.json'
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}

    return payload if isinstance(payload, dict) else {}


def discover_case_metadata_years() -> list[int]:
    if not CASE_METADATA_ROOT.exists():
        return []

    years = []
    for path in CASE_METADATA_ROOT.glob('*.json'):
        try:
            years.append(int(path.stem))
        except ValueError:
            continue
    return sorted(set(years), reverse=True)


class CaseMixListView(CatalogScopeMixin, TemplateView):
    template_name = 'catalog/case_mix_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.apply_profile_scope(HotWheelsModel.objects.all()).exclude(case_codes='')

        year_map: dict[int, dict] = {}
        for model in queryset.only('year', 'case_codes', 'special_tag'):
            if model.year is None:
                continue
            year_bucket = year_map.setdefault(
                model.year,
                {
                    'year': model.year,
                    'case_codes': set(),
                    'model_count': 0,
                    'th_count': 0,
                    'sth_count': 0,
                },
            )
            year_bucket['model_count'] += 1
            for case_code in model.case_code_list:
                year_bucket['case_codes'].add(case_code)
            if model.special_tag == 'Treasure Hunt':
                year_bucket['th_count'] += 1
            elif model.special_tag == 'Super Treasure Hunt':
                year_bucket['sth_count'] += 1

        all_years = sorted(set(year_map) | set(discover_case_metadata_years()), reverse=True)
        case_years = []
        for year in all_years:
            row = year_map.get(
                year,
                {
                    'year': year,
                    'case_codes': set(),
                    'model_count': 0,
                    'th_count': 0,
                    'sth_count': 0,
                },
            )
            metadata = load_case_year_metadata(year)
            meta_cases = metadata.get('cases', {}) if isinstance(metadata.get('cases', {}), dict) else {}
            case_codes = sorted(set(row['case_codes']) | {code for code in meta_cases if code})
            case_links = [
                {
                    'code': case_code,
                    'url': reverse('catalog:case-mix-detail', args=[year, case_code.lower()]),
                    'teaser': str(
                        meta_cases.get(case_code, {}).get('teaser', '')
                        if isinstance(meta_cases.get(case_code, {}), dict) else ''
                    ).strip(),
                }
                for case_code in case_codes
            ]
            case_years.append(
                {
                    'year': year,
                    'case_links': case_links,
                    'case_count': len(case_codes),
                    'headline': str(metadata.get('headline', '')).strip(),
                    'intro': str(metadata.get('intro', '')).strip(),
                }
            )

        context['case_years'] = case_years
        context['selected_scope'] = self.get_scope_mode()
        return context


class CaseMixDetailView(CatalogScopeMixin, TemplateView):
    template_name = 'catalog/case_mix_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        year = int(self.kwargs['year'])
        case_code = ModelListView.normalize_case_code(self.kwargs['case_code'])
        queryset = self.apply_profile_scope(
            HotWheelsModel.objects.filter(year=year, category='Mainline')
        ).filter(ModelListView.build_case_filter(case_code)).order_by('number', 'model_name')

        metadata = load_case_year_metadata(year)
        case_meta_map = metadata.get('cases', {}) if isinstance(metadata.get('cases', {}), dict) else {}
        case_meta = case_meta_map.get(case_code, {}) if isinstance(case_meta_map.get(case_code, {}), dict) else {}

        if not queryset.exists() and not case_meta:
            raise Http404('Case mix not found.')

        th_models = [model for model in queryset if model.special_tag == 'Treasure Hunt']
        sth_models = [model for model in queryset if model.special_tag == 'Super Treasure Hunt']

        context['year'] = year
        context['case_code'] = case_code
        context['models'] = queryset
        context['case_stats'] = {
            'model_count': queryset.count(),
            'th_count': len(th_models),
            'sth_count': len(sth_models),
        }
        context['th_models'] = th_models
        context['sth_models'] = sth_models
        context['case_meta'] = {
            'title': str(case_meta.get('title', '')).strip(),
            'description': str(case_meta.get('description', '')).strip(),
            'notes': str(case_meta.get('notes', '')).strip(),
            'th_notes': str(case_meta.get('th_notes', '')).strip(),
            'sth_notes': str(case_meta.get('sth_notes', '')).strip(),
            'source_url': str(case_meta.get('source_url', '')).strip(),
        }
        context['back_to_list_url'] = reverse('catalog:case-mix-list')
        context['catalog_url'] = f"{reverse('catalog:model-list')}?year={year}&category=Mainline&case_code={case_code}"
        context['selected_scope'] = self.get_scope_mode()
        return context
