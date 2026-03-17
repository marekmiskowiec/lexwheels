from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import User


class EmailOrLoginBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get(User.USERNAME_FIELD) or '').strip()
        if not identifier or password is None:
            return None

        user = (
            User.objects.filter(Q(email__iexact=identifier) | Q(login__iexact=identifier))
            .order_by('id')
            .first()
        )
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
