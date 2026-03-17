from django.urls import path

from .views import ModelDetailView, ModelListView

app_name = 'catalog'

urlpatterns = [
    path('', ModelListView.as_view(), name='model-list'),
    path('models/<int:pk>/', ModelDetailView.as_view(), name='model-detail'),
]
