from django.urls import path

from .views import CatalogCoverageView, ModelDetailView, ModelListView

app_name = 'catalog'

urlpatterns = [
    path('', ModelListView.as_view(), name='model-list'),
    path('zakres-bazy/', CatalogCoverageView.as_view(), name='coverage'),
    path('models/<int:pk>/', ModelDetailView.as_view(), name='model-detail'),
]
