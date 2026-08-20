from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        # Registers the system checks; importing for the side effect is how
        # Django expects checks to be wired up.
        from . import checks  # noqa: F401
