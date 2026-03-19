from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.views.generic import DetailView, ListView
import shlex
from urllib.parse import urlencode

from collections_app.forms import CatalogQuickAddForm, CollectionBatchAddForm

from .models import HotWheelsModel


CATALOG_FILTER_SESSION_KEY = 'catalog_filters'
CATALOG_SCOPE_PROFILE = 'profile'
CATALOG_SCOPE_ALL = 'all'


class ModelListView(ListView):
    model = HotWheelsModel
    template_name = 'catalog/model_list.html'
    context_object_name = 'models'
    paginate_by = 24

    def get(self, request, *args, **kwargs):
        base_url = request.path
        if request.GET.get('save_filters') == '1':
            filters = {
                key: request.GET.get(key, '').strip()
                for key in (
                    'q', 'brand', 'series', 'year', 'category', 'exclusive_store', 'special_tag', 'sort', 'scope'
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

    def get_queryset(self):
        queryset = HotWheelsModel.objects.all()
        queryset = self.apply_profile_scope(queryset)
        raw_query = self.request.GET.get('q', '').strip()
        parsed_query = self.parse_search_query(raw_query)
        query = parsed_query['text']
        series = self.request.GET.get('series', '').strip() or parsed_query['series']
        brand = self.request.GET.get('brand', '').strip() or parsed_query['brand']
        year = self.request.GET.get('year', '').strip() or parsed_query['year']
        category = self.request.GET.get('category', '').strip() or parsed_query['category']
        exclusive_store = self.request.GET.get('exclusive_store', '').strip() or parsed_query['exclusive_store']
        special_tag = self.request.GET.get('special_tag', '').strip() or parsed_query['special_tag']
        sort = self.request.GET.get('sort', 'number').strip()

        if query:
            queryset = queryset.filter(
                Q(toy__icontains=query)
                | Q(number__icontains=query)
                | Q(model_name__icontains=query)
                | Q(brand__icontains=query)
                | Q(series__icontains=query)
            )
        if brand:
            queryset = queryset.filter(brand=brand)
        if series:
            queryset = queryset.filter(series=series)
        if year.isdigit():
            queryset = queryset.filter(year=int(year))
        if category:
            queryset = queryset.filter(category=category)
        if exclusive_store:
            queryset = queryset.filter(exclusive_store=exclusive_store)
        if special_tag:
            queryset = queryset.filter(special_tag=special_tag)

        sort_options = {
            'number': ('number', 'model_name'),
            'year': ('year', 'number', 'model_name'),
            'category': ('category', 'year', 'number', 'model_name'),
            'exclusive': ('exclusive_store', 'special_tag', 'year', 'number', 'model_name'),
            'name': ('model_name',),
        }
        return queryset.order_by(*sort_options.get(sort, sort_options['number']))

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
            else:
                free_text_tokens.append(token)

        parsed['text'] = ' '.join(free_text_tokens).strip()
        return parsed

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filtered_count = context['page_obj'].paginator.count if context.get('page_obj') else len(context['models'])
        total_queryset = HotWheelsModel.objects.all()
        scope_mode = self.get_scope_mode()
        scoped_total_queryset = self.apply_profile_scope(HotWheelsModel.objects.all())
        filter_options_queryset = scoped_total_queryset if scope_mode == CATALOG_SCOPE_PROFILE else total_queryset
        raw_query = self.request.GET.get('q', '').strip()
        parsed_query = self.parse_search_query(raw_query)
        context['query'] = raw_query
        context['selected_scope'] = scope_mode
        context['selected_brand'] = self.request.GET.get('brand', '').strip() or parsed_query['brand']
        context['selected_series'] = self.request.GET.get('series', '').strip() or parsed_query['series']
        context['selected_year'] = self.request.GET.get('year', '').strip() or parsed_query['year']
        context['selected_category'] = self.request.GET.get('category', '').strip() or parsed_query['category']
        context['selected_exclusive_store'] = self.request.GET.get('exclusive_store', '').strip() or parsed_query['exclusive_store']
        context['selected_special_tag'] = self.request.GET.get('special_tag', '').strip() or parsed_query['special_tag']
        context['selected_sort'] = self.request.GET.get('sort', 'number').strip() or 'number'
        context['current_path'] = self.request.get_full_path()
        context['series_options'] = (
            filter_options_queryset.exclude(series='')
            .values_list('series', flat=True)
            .distinct()
            .order_by('series')
        )
        context['brand_options'] = (
            filter_options_queryset.exclude(brand='')
            .values_list('brand', flat=True)
            .distinct()
            .order_by('brand')
        )
        context['year_options'] = (
            filter_options_queryset.exclude(year__isnull=True)
            .values_list('year', flat=True)
            .distinct()
            .order_by('year')
        )
        context['category_options'] = (
            filter_options_queryset.exclude(category='')
            .values_list('category', flat=True)
            .distinct()
            .order_by('category')
        )
        context['exclusive_store_options'] = (
            filter_options_queryset.exclude(exclusive_store='')
            .values_list('exclusive_store', flat=True)
            .distinct()
            .order_by('exclusive_store')
        )
        context['special_tag_options'] = (
            filter_options_queryset.exclude(special_tag='')
            .values_list('special_tag', flat=True)
            .distinct()
            .order_by('special_tag')
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
            context['quick_add_form'] = CatalogQuickAddForm(owner=self.request.user, initial={'next': self.request.get_full_path()})
        context['saved_filters'] = self.request.session.get(CATALOG_FILTER_SESSION_KEY, {})
        return context


class ModelDetailView(DetailView):
    model = HotWheelsModel
    template_name = 'catalog/model_detail.html'
    context_object_name = 'model_obj'
