from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import login
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import CatalogScopeForm, ProfileForm, UserRegistrationForm
from .models import User
from collections_app.models import CollectionItem


class RegisterView(CreateView):
    form_class = UserRegistrationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('collections:dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = User
    template_name = 'accounts/profile_detail.html'
    context_object_name = 'profile_user'

    def get_object(self, queryset=None):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_profile_context(self.request.user, public_only=False))
        context['is_own_profile'] = True
        return context


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    form_class = ProfileForm
    template_name = 'accounts/profile_form.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self, queryset=None):
        return self.request.user


class CatalogScopeUpdateView(LoginRequiredMixin, UpdateView):
    form_class = CatalogScopeForm
    template_name = 'accounts/catalog_scope_form.html'
    success_url = reverse_lazy('accounts:catalog-scope')

    def get_object(self, queryset=None):
        return self.request.user


class PublicProfileView(DetailView):
    model = User
    template_name = 'accounts/profile_detail.html'
    context_object_name = 'profile_user'

    def get_object(self, queryset=None):
        return get_object_or_404(User, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_profile_context(self.object, public_only=True))
        context['is_own_profile'] = self.request.user.is_authenticated and self.request.user == self.object
        return context


class PublicCollectorListView(ListView):
    def get(self, request, *args, **kwargs):
        return redirect(f"{reverse('collections:community')}?view=collectors")


def build_profile_context(user: User, public_only: bool) -> dict:
    collections = user.collections.all()
    if public_only:
        collections = collections.filter(visibility='public')

    items = CollectionItem.objects.filter(collection__owner=user)
    if public_only:
        items = items.filter(collection__visibility='public')

    stats = items.aggregate(
        total_quantity=Sum('quantity'),
        favorite_count=Count('id', filter=Q(is_favorite=True)),
    )
    return {
        'collections_list': collections.order_by('name'),
        'stats': {
            'collection_count': collections.count(),
            'item_count': items.count(),
            'total_quantity': stats['total_quantity'] or 0,
            'favorite_count': stats['favorite_count'] or 0,
        },
    }
