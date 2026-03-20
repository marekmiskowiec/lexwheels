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
        return (login or '').strip()

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
        provided_name = extra_fields.pop('display_name', '')
        login = self.normalize_login(extra_fields.pop('login', '') or provided_name) or self.generate_login(email)
        user = self.model(email=email, **extra_fields)
        user.login = login
        user.display_name = login
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
    first_name = None
    last_name = None
    email = models.EmailField(unique=True)
    login = models.CharField(max_length=80, unique=True)
    display_name = models.CharField(max_length=80, blank=True)
    bio = models.CharField(max_length=200, blank=True)
    youtube_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    avatar_key = models.CharField(max_length=32, choices=AVATAR_CHOICES, default='flame-red')
    catalog_scope_enabled = models.BooleanField(default=False)
    catalog_scope_brands = models.JSONField(default=list, blank=True)
    catalog_scope_categories = models.JSONField(default=list, blank=True)
    catalog_scope_year_from = models.PositiveIntegerField(blank=True, null=True)
    catalog_scope_year_to = models.PositiveIntegerField(blank=True, null=True)
    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self) -> str:
        return self.public_name

    @property
    def public_name(self) -> str:
        return self.display_name or self.login or self.email

    @property
    def avatar_static_path(self) -> str:
        return f'accounts/avatars/{self.avatar_key}.svg'

    @staticmethod
    def normalize_scope_values(values) -> list[str]:
        normalized = []
        for value in values or []:
            cleaned = str(value).strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    def apply_catalog_scope(self, queryset):
        if not self.catalog_scope_enabled:
            return queryset

        brands = self.normalize_scope_values(self.catalog_scope_brands)
        categories = self.normalize_scope_values(self.catalog_scope_categories)

        if brands:
            queryset = queryset.filter(brand__in=brands)
        if categories:
            queryset = queryset.filter(category__in=categories)
        if self.catalog_scope_year_from:
            queryset = queryset.filter(year__gte=self.catalog_scope_year_from)
        if self.catalog_scope_year_to:
            queryset = queryset.filter(year__lte=self.catalog_scope_year_to)
        return queryset

    @property
    def catalog_scope_summary(self) -> list[str]:
        summary = []
        brands = self.normalize_scope_values(self.catalog_scope_brands)
        categories = self.normalize_scope_values(self.catalog_scope_categories)
        if brands:
            summary.append(f"Marki: {', '.join(brands)}")
        if categories:
            summary.append(f"Kategorie: {', '.join(categories)}")
        if self.catalog_scope_year_from or self.catalog_scope_year_to:
            summary.append(
                f"Lata: {self.catalog_scope_year_from or 'od początku'} - {self.catalog_scope_year_to or 'bez końca'}"
            )
        return summary
