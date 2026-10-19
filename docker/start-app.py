from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.utils import send_from_directory
from werkzeug.serving import run_simple
from domain_admin.main import app as api_app

FRONTEND_DIR = '/srv/frontend'


def static_app(environ, start_response):
    path = environ.get('PATH_INFO', '').lstrip('/')
    target = path if path and not path.startswith(('api/', 'temp/')) else 'index.html'
    response = send_from_directory(FRONTEND_DIR, target)
    return response(environ, start_response)


application = DispatcherMiddleware(static_app, {
    '/api': api_app,
    '/test': api_app,
    '/temp': api_app,
})


if __name__ == '__main__':
    run_simple('0.0.0.0', 8000, application, use_reloader=False, use_debugger=False)
