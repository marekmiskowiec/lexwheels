import json
import shlex
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from collections_app.forms import CollectionBatchAddForm

from .models import HotWheelsModel


CATALOG_FILTER_SESSION_KEY = 'catalog_filters'
CATALOG_SCOPE_PROFILE = 'profile'
CATALOG_SCOPE_ALL = 'all'
CASE_METADATA_ROOT = settings.PROJECT_ROOT / 'data' / 'case-highlights' / 'hot-wheels' / 'mainline'


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
                    'q', 'brand', 'series', 'year', 'category', 'exclusive_store', 'special_tag', 'case_code', 'sort', 'scope'
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
            queryset = queryset.filter(exclusive_store=filters['exclusive_store'])
        if filters['special_tag'] and 'special_tag' not in exclude_filters:
            queryset = queryset.filter(special_tag=filters['special_tag'])
        if filters['case_code'] and 'case_code' not in exclude_filters:
            queryset = queryset.filter(self.build_case_filter(filters['case_code']))

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


class ModelDetailView(DetailView):
    model = HotWheelsModel
    template_name = 'catalog/model_detail.html'
    context_object_name = 'model_obj'

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
        return context


class CatalogCoverageView(CatalogScopeMixin, TemplateView):
    template_name = 'catalog/coverage.html'

    @staticmethod
    def normalize_group_name(category: str, series: str) -> tuple[str, bool]:
        category = (category or '').strip()
        series = (series or '').strip()

        if category == 'Mainline':
            return category, False
        if series and ' - Mix ' in series:
            return series.split(' - Mix ', 1)[0], True
        if series:
            return series, False
        return category or 'Bez kategorii', False

    @staticmethod
    def build_catalog_url(scope_mode: str, category: str, year: int | None, group_name: str, uses_search: bool) -> str:
        params: dict[str, str | int] = {'scope': scope_mode}
        if year:
            params['year'] = year
        if category:
            params['category'] = category

        if uses_search:
            params['q'] = group_name
        elif category != group_name:
            params['series'] = group_name

        return f"{reverse('catalog:model-list')}?{urlencode(params)}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scope_mode = self.get_scope_mode()
        queryset = self.apply_profile_scope(HotWheelsModel.objects.all())
        rows = queryset.values('brand', 'category', 'series', 'year').order_by('brand', 'category', 'series', 'year')

        coverage_map: dict[str, dict[str, dict]] = {}
        total_years = set()

        for row in rows:
            brand = (row['brand'] or 'Nieznana marka').strip()
            category = (row['category'] or 'Bez kategorii').strip()
            year = row['year']
            group_name, uses_search = self.normalize_group_name(category, row['series'])

            brand_bucket = coverage_map.setdefault(brand, {})
            group_bucket = brand_bucket.setdefault(
                group_name,
                {
                    'name': group_name,
                    'category': category,
                    'year_rows': {},
                    'uses_search': uses_search,
                },
            )
            if year not in group_bucket['year_rows']:
                group_bucket['year_rows'][year] = {
                    'year': year,
                    'count': 0,
                    'url': self.build_catalog_url(scope_mode, category, year, group_name, group_bucket['uses_search']),
                }
            group_bucket['year_rows'][year]['count'] += 1
            if year is not None:
                total_years.add(year)

        coverage_groups = []
        for brand, groups in coverage_map.items():
            items = []
            model_total = 0
            for group in sorted(groups.values(), key=lambda item: (item['category'].lower(), item['name'].lower())):
                year_rows = sorted(
                    group['year_rows'].values(),
                    key=lambda item: (item['year'] is None, item['year']),
                )
                group_count = sum(row['count'] for row in year_rows)
                model_total += group_count
                items.append(
                    {
                        'name': group['name'],
                        'category': group['category'],
                        'year_rows': year_rows,
                        'group_count': group_count,
                    }
                )
            coverage_groups.append(
                {
                    'brand': brand,
                    'items': items,
                    'model_total': model_total,
                    'group_count': len(items),
                }
            )

        coverage_groups.sort(key=lambda item: item['brand'].lower())
        context['coverage_groups'] = coverage_groups
        context['coverage_stats'] = {
            'brand_count': len(coverage_groups),
            'group_count': sum(group['group_count'] for group in coverage_groups),
            'year_count': len(total_years),
            'model_count': queryset.count(),
        }
        context['selected_scope'] = scope_mode
        context['scope_summary'] = self.request.user.catalog_scope_summary if (
            self.request.user.is_authenticated and scope_mode == CATALOG_SCOPE_PROFILE
        ) else []
        return context


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
