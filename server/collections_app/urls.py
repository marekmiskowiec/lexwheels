from django.urls import path

from .views import (
    CollectionBatchAddView,
    CollectionBatchDeleteView,
    CollectionCreateView,
    CollectionDeleteView,
    CollectionDetailView,
    CollectionExportView,
    CollectionItemCreateView,
    CollectionItemDeleteView,
    CollectionItemUpdateView,
    CollectionUpdateView,
    DashboardView,
    PublicCollectionListView,
)

app_name = 'collections'

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('public/', PublicCollectionListView.as_view(), name='public-collections'),
    path('batch-add/', CollectionBatchAddView.as_view(), name='batch-add'),
    path('new/', CollectionCreateView.as_view(), name='collection-create'),
    path('<int:pk>/', CollectionDetailView.as_view(), name='collection-detail'),
    path('<int:pk>/items/batch-delete/', CollectionBatchDeleteView.as_view(), name='item-batch-delete'),
    path('<int:pk>/export/<str:fmt>/', CollectionExportView.as_view(), name='collection-export'),
    path('<int:pk>/edit/', CollectionUpdateView.as_view(), name='collection-update'),
    path('<int:pk>/delete/', CollectionDeleteView.as_view(), name='collection-delete'),
    path('<int:collection_pk>/items/new/', CollectionItemCreateView.as_view(), name='item-create'),
    path('items/<int:pk>/edit/', CollectionItemUpdateView.as_view(), name='item-update'),
    path('items/<int:pk>/delete/', CollectionItemDeleteView.as_view(), name='item-delete'),
]
