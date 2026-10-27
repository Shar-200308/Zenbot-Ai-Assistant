import os

from django.core.wsgi import get_wsgi_application as _get_django_wsgi_app

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Zenbot.settings')

_raw_app = None


def get_wsgi_application():
    global _raw_app
    if _raw_app is None:
        _raw_app = _get_django_wsgi_app()

    def wrapped_app(environ, start_response):
        proto = environ.get('HTTP_X_FORWARDED_PROTO')
        if proto:
            environ['wsgi.url_scheme'] = proto.split(',')[0].strip()
        return _raw_app(environ, start_response)

    return wrapped_app


application = get_wsgi_application()

