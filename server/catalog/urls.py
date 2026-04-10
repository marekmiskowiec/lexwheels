from django.urls import path

from .views import (
    CaseMixDetailView,
    CaseMixListView,
    CatalogAdminDashboardView,
    ModelDetailView,
    ModelListView,
    ModelSearchSuggestionsView,
    MissingPackagingImageListView,
    AssignGenericImageView,
    UnassignedImageListView,
    ReassignPackagingImageView,
    AssignedImageListView,
    CompleteImageListView,
    ToggleImageVerificationView,
    ImportCatalogImageView,
    DeleteCatalogImageView,
)

app_name = 'catalog'

urlpatterns = [
    path('', ModelListView.as_view(), name='model-list'),
    path('suggestions/', ModelSearchSuggestionsView.as_view(), name='model-search-suggestions'),
    path('case-mixy/', CaseMixListView.as_view(), name='case-mix-list'),
    path('case-mixy/<int:year>/<slug:case_code>/', CaseMixDetailView.as_view(), name='case-mix-detail'),
    path('panel-admina/', CatalogAdminDashboardView.as_view(), name='admin-dashboard'),
    path('brakujace-zdjecia/', MissingPackagingImageListView.as_view(), name='missing-packaging-images'),
    path('nieprzypisane-zdjecia/', UnassignedImageListView.as_view(), name='unassigned-images'),
    path('przypisane-zdjecia/', AssignedImageListView.as_view(), name='assigned-images'),
    path('komplet-zdjec/', CompleteImageListView.as_view(), name='complete-images'),
    path('nieprzypisane-zdjecia/<int:pk>/<slug:packaging_state>/', AssignGenericImageView.as_view(), name='assign-generic-image'),
    path('zdjecia/<int:pk>/usun/<slug:packaging_state>/', DeleteCatalogImageView.as_view(), name='delete-image'),
    path('zdjecia/<int:pk>/<slug:source_packaging_state>/<slug:target_packaging_state>/', ReassignPackagingImageView.as_view(), name='reassign-packaging-image'),
    path('zdjecia/<int:pk>/verified/', ToggleImageVerificationView.as_view(), name='toggle-image-verification'),
    path('zdjecia/<int:pk>/import-url/', ImportCatalogImageView.as_view(), name='import-image-from-url'),
    path('models/<int:pk>/', ModelDetailView.as_view(), name='model-detail'),
]
