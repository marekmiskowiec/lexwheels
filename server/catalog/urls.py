from django.urls import path

from .views import (
    CaseMixDetailView,
    CaseMixListView,
    CatalogCoverageView,
    ModelDetailView,
    ModelListView,
    ModelSearchSuggestionsView,
)

app_name = 'catalog'

urlpatterns = [
    path('', ModelListView.as_view(), name='model-list'),
    path('suggestions/', ModelSearchSuggestionsView.as_view(), name='model-search-suggestions'),
    path('case-mixy/', CaseMixListView.as_view(), name='case-mix-list'),
    path('case-mixy/<int:year>/<slug:case_code>/', CaseMixDetailView.as_view(), name='case-mix-detail'),
    path('zakres-bazy/', CatalogCoverageView.as_view(), name='coverage'),
    path('models/<int:pk>/', ModelDetailView.as_view(), name='model-detail'),
]
