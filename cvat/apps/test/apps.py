from django.apps import AppConfig


class TestConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cvat.apps.test'

    def ready(self):
        import cvat.apps.test.signals  # noqa: F401
