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

        if query:
            queryset = queryset.filter(
                Q(toy__icontains=query)
                | Q(number__icontains=query)
                | Q(model_name__icontains=query)
                | Q(series__icontains=query)
            )
        if series:
            queryset = queryset.filter(series=series)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '').strip()
        context['selected_series'] = self.request.GET.get('series', '').strip()
        context['current_path'] = self.request.get_full_path()
        context['series_options'] = (
            HotWheelsModel.objects.exclude(series='')
            .values_list('series', flat=True)
            .distinct()
            .order_by('series')
        )
        if self.request.user.is_authenticated:
            context['batch_add_form'] = CollectionBatchAddForm(owner=self.request.user, initial={'next': self.request.get_full_path()})
        return context


class ModelDetailView(DetailView):
    model = HotWheelsModel
    template_name = 'catalog/model_detail.html'
    context_object_name = 'model_obj'
