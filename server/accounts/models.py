from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


AVATAR_CHOICES = (
    ('flame-red', 'Flame Red'),
    ('track-orange', 'Track Orange'),
    ('garage-blue', 'Garage Blue'),
    ('mint-green', 'Mint Green'),
    ('sunburst-yellow', 'Sunburst Yellow'),
    ('midnight-black', 'Midnight Black'),
    ('chrome-silver', 'Chrome Silver'),
    ('purple-rush', 'Purple Rush'),
    ('teal-speed', 'Teal Speed'),
    ('sand-racer', 'Sand Racer'),
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def normalize_login(self, login):
        return (login or '').strip().lower()

    def generate_login(self, email):
        base = self.normalize_login(email.partition('@')[0]) or 'user'
        candidate = base
        suffix = 1

        while self.model.objects.filter(login__iexact=candidate).exists():
            suffix += 1
            candidate = f'{base}{suffix}'

        return candidate

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        login = self.normalize_login(extra_fields.pop('login', '')) or self.generate_login(email)
        user = self.model(email=email, **extra_fields)
        user.login = login
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    login = models.CharField(max_length=80, unique=True)
    display_name = models.CharField(max_length=80, blank=True)
    bio = models.TextField(blank=True)
    avatar_key = models.CharField(max_length=32, choices=AVATAR_CHOICES, default='flame-red')
    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self) -> str:
        return self.email

    @property
    def public_name(self) -> str:
        return self.display_name or self.get_full_name() or self.email

    @property
    def avatar_static_path(self) -> str:
        return f'accounts/avatars/{self.avatar_key}.svg'
