from django.db.models import Q
from django.views.generic import DetailView, ListView

from collections_app.forms import CollectionBatchAddForm

from .models import HotWheelsModel


class ModelListView(ListView):
    model = HotWheelsModel
    template_name = 'catalog/model_list.html'
    context_object_name = 'models'
    paginate_by = 24

    def get_queryset(self):
        queryset = HotWheelsModel.objects.all()
        query = self.request.GET.get('q', '').strip()
        series = self.request.GET.get('series', '').strip()
        year = self.request.GET.get('year', '').strip()
        category = self.request.GET.get('category', '').strip()
        sort = self.request.GET.get('sort', 'number').strip()

        if query:
            queryset = queryset.filter(
                Q(toy__icontains=query)
                | Q(number__icontains=query)
                | Q(model_name__icontains=query)
                | Q(series__icontains=query)
            )
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
        return context


class ModelDetailView(DetailView):
    model = HotWheelsModel
    template_name = 'catalog/model_detail.html'
    context_object_name = 'model_obj'
