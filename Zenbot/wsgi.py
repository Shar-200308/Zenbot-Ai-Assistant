import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Zenbot.settings')

_django_app = get_wsgi_application()


def application(environ, start_response):
    # Ensure X-Forwarded-Proto is reflected in wsgi.url_scheme for reverse proxies (Render, Cloudflare, etc.)
    proto = environ.get('HTTP_X_FORWARDED_PROTO')
    if proto:
        environ['wsgi.url_scheme'] = proto.split(',')[0].strip()
    return _django_app(environ, start_response)

