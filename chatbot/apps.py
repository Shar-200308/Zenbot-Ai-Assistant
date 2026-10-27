import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ChatbotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chatbot'
    verbose_name = "Chatbot Application"

    def ready(self):
        """
        Fix: Secrets validation on startup.
        Warns loudly when insecure default credentials are detected so they are
        caught in development before reaching production.
        No external secrets manager required — works with plain environment variables.
        """
        from django.conf import settings

        _INSECURE_SECRET_PATTERNS = [
            'django-insecure',
            'your-secret-key',
            'changeme',
            'secret',
        ]
        _INSECURE_GEMINI_PATTERNS = [
            '', 'your-gemini-api-key', 'AIzaSy_EXAMPLE',
        ]
        _INSECURE_DB_PATTERNS = [
            'your-db', 'postgres://user:password',
        ]
        _INSECURE_EMAIL_PATTERNS = [
            'your-email@gmail.com', 'your-app-password', '',
        ]

        warnings = []

        # 1. Django SECRET_KEY
        secret_key = getattr(settings, 'SECRET_KEY', '')
        if any(p in secret_key.lower() for p in _INSECURE_SECRET_PATTERNS):
            warnings.append(
                "SECRET_KEY appears to be a default/insecure value. "
                "Set a strong random SECRET_KEY in your .env for production."
            )

        # 2. Gemini API key
        gemini_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
        if gemini_key in _INSECURE_GEMINI_PATTERNS:
            warnings.append(
                "GEMINI_API_KEY is not set. Add GEMINI_API_KEY=<your-key> to .env."
            )

        # 3. Email credentials (skip warning in test mode)
        email_user = getattr(settings, 'EMAIL_HOST_USER', '')
        email_pass = getattr(settings, 'EMAIL_HOST_PASSWORD', '')
        if email_user in _INSECURE_EMAIL_PATTERNS or email_pass in _INSECURE_EMAIL_PATTERNS:
            warnings.append(
                "EMAIL_HOST_USER or EMAIL_HOST_PASSWORD is using a default placeholder. "
                "Set real SMTP credentials in .env before enabling email features."
            )

        # 4. DEBUG=True in production (check ALLOWED_HOSTS as proxy for production)
        allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', ['*'])
        if getattr(settings, 'DEBUG', True) and allowed_hosts and '*' not in allowed_hosts:
            warnings.append(
                "DEBUG=True is set while ALLOWED_HOSTS is restricted — "
                "this looks like a production environment. Set DEBUG=False in .env."
            )

        # Emit all warnings
        for w in warnings:
            logger.warning("[SECURITY] %s", w)

        if warnings:
            logger.warning(
                "[SECURITY] %d security misconfiguration(s) detected above. "
                "See .env.example for correct configuration.",
                len(warnings),
            )
