from django.db.models import Count
from django.http import JsonResponse
from django.views.generic import TemplateView

from catalog.models import HotWheelsModel
from collections_app.models import Collection, CollectionItem
from collections_app.views import build_collection_stats_context, build_completion_context


def healthcheck(request):
    return JsonResponse({'status': 'ok'})


class HomeView(TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total_models = HotWheelsModel.objects.count()
        recent_models = HotWheelsModel.objects.order_by('-year', '-pk')[:8]

        context['catalog_stats'] = {
            'total_models': total_models,
            'brand_count': HotWheelsModel.objects.exclude(brand='').values('brand').distinct().count(),
            'year_count': HotWheelsModel.objects.exclude(year__isnull=True).values('year').distinct().count(),
            'category_count': HotWheelsModel.objects.exclude(category='').values('category').distinct().count(),
        }
        context['recent_models'] = recent_models
        context['public_stats'] = {
            'public_collections': Collection.objects.filter(visibility=Collection.VISIBILITY_PUBLIC).count(),
            'collector_count': Collection.objects.filter(visibility=Collection.VISIBILITY_PUBLIC)
            .values('owner_id')
            .distinct()
            .count(),
        }
        context['featured_series'] = (
            HotWheelsModel.objects.exclude(series='')
            .values('series')
            .annotate(total=Count('id'))
            .order_by('-total', 'series')[:6]
        )

        if self.request.user.is_authenticated:
            collections = Collection.objects.filter(owner=self.request.user).prefetch_related('items')
            owner_items = CollectionItem.objects.filter(collection__owner=self.request.user)
            stats_context = build_collection_stats_context(owner_items)
            completion_context = build_completion_context(owner_items)
            context['user_summary'] = {
                'collection_count': collections.filter(kind=Collection.KIND_OWNED).count(),
                'wishlist_count': collections.filter(kind=Collection.KIND_WISHLIST).count(),
                'item_count': stats_context['stats']['item_count'],
                'variant_count': stats_context['stats']['variant_count'],
                'favorite_count': stats_context['stats']['favorite_count'],
                'total_quantity': stats_context['stats']['total_quantity'],
            }
            context['completion'] = completion_context['completion']
            context['completion_by_series'] = completion_context['completion_by_series'][:5]
            context['focus_collections'] = collections.annotate(item_total=Count('items')).order_by('-item_total', 'name')[:4]

        return context
