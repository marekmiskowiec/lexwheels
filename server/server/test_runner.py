from django.conf import settings
from django.test.runner import DiscoverRunner


class AppAwareDiscoverRunner(DiscoverRunner):
    def build_suite(self, test_labels=None, extra_tests=None, **kwargs):
        labels = test_labels
        if not labels:
            labels = [
                app.rsplit('.', 1)[0]
                for app in settings.INSTALLED_APPS
                if app in {'accounts', 'catalog', 'collections_app'}
            ]
        return super().build_suite(test_labels=labels, extra_tests=extra_tests, **kwargs)
