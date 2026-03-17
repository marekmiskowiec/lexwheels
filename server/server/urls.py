from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.forms import EmailAuthenticationForm
from .views import healthcheck

urlpatterns = [
    path('admin/', admin.site.urls),
    path('healthz/', healthcheck, name='healthcheck'),
    path('', include('catalog.urls')),
    path('collections/', include('collections_app.urls')),
    path('accounts/', include('accounts.urls')),
    path('accounts/login/', auth_views.LoginView.as_view(authentication_form=EmailAuthenticationForm), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/password-reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('accounts/password-reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('accounts/reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
