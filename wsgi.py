"""
WSGI entrypoint para Gunicorn
"""

from core.app_factory import create_app

app = create_app()
server = app.server
