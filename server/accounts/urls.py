from django.urls import path

from .views import ProfileDetailView, ProfileUpdateView, PublicCollectorListView, PublicProfileView, RegisterView

app_name = 'accounts'

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('profile/', ProfileDetailView.as_view(), name='profile'),
    path('profile/edit/', ProfileUpdateView.as_view(), name='profile-edit'),
    path('collectors/', PublicCollectorListView.as_view(), name='collector-list'),
    path('u/<int:pk>/', PublicProfileView.as_view(), name='public-profile'),
]
