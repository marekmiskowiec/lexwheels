from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.views.generic import DetailView, ListView
from urllib.parse import urlencode

from collections_app.forms import CatalogQuickAddForm, CollectionBatchAddForm

from .models import HotWheelsModel


CATALOG_FILTER_SESSION_KEY = 'catalog_filters'


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
                for key in ('q', 'brand', 'series', 'year', 'category', 'sort')
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
        queryset = HotWheelsModel.objects.all()
        query = self.request.GET.get('q', '').strip()
        series = self.request.GET.get('series', '').strip()
        brand = self.request.GET.get('brand', '').strip()
        year = self.request.GET.get('year', '').strip()
        category = self.request.GET.get('category', '').strip()
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

        sort_options = {
            'number': ('number', 'model_name'),
            'year': ('year', 'number', 'model_name'),
            'category': ('category', 'year', 'number', 'model_name'),
            'name': ('model_name',),
        }
        return queryset.order_by(*sort_options.get(sort, sort_options['number']))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '').strip()
        context['selected_brand'] = self.request.GET.get('brand', '').strip()
        context['selected_series'] = self.request.GET.get('series', '').strip()
        context['selected_year'] = self.request.GET.get('year', '').strip()
        context['selected_category'] = self.request.GET.get('category', '').strip()
        context['selected_sort'] = self.request.GET.get('sort', 'number').strip() or 'number'
        context['current_path'] = self.request.get_full_path()
        context['series_options'] = (
            HotWheelsModel.objects.exclude(series='')
            .values_list('series', flat=True)
            .distinct()
            .order_by('series')
        )
        context['brand_options'] = (
            HotWheelsModel.objects.exclude(brand='')
            .values_list('brand', flat=True)
            .distinct()
            .order_by('brand')
        )
        context['year_options'] = (
            HotWheelsModel.objects.exclude(year__isnull=True)
            .values_list('year', flat=True)
            .distinct()
            .order_by('year')
        )
        context['category_options'] = (
            HotWheelsModel.objects.exclude(category='')
            .values_list('category', flat=True)
            .distinct()
            .order_by('category')
        )
        if self.request.user.is_authenticated:
            context['batch_add_form'] = CollectionBatchAddForm(owner=self.request.user, initial={'next': self.request.get_full_path()})
            context['quick_add_form'] = CatalogQuickAddForm(owner=self.request.user, initial={'next': self.request.get_full_path()})
        context['saved_filters'] = self.request.session.get(CATALOG_FILTER_SESSION_KEY, {})
        return context


class ModelDetailView(DetailView):
    model = HotWheelsModel
    template_name = 'catalog/model_detail.html'
    context_object_name = 'model_obj'
