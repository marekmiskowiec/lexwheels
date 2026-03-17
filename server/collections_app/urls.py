from django.urls import path

from .views import (
    CollectionCreateView,
    CollectionDetailView,
    CollectionItemCreateView,
    CollectionItemDeleteView,
    CollectionItemUpdateView,
    DashboardView,
)

app_name = 'collections'

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('new/', CollectionCreateView.as_view(), name='collection-create'),
    path('<int:pk>/', CollectionDetailView.as_view(), name='collection-detail'),
    path('<int:collection_pk>/items/new/', CollectionItemCreateView.as_view(), name='item-create'),
    path('items/<int:pk>/edit/', CollectionItemUpdateView.as_view(), name='item-update'),
    path('items/<int:pk>/delete/', CollectionItemDeleteView.as_view(), name='item-delete'),
]
