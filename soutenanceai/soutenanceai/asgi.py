"""Configuration ASGI pour SoutenanceAI (HTTP + WebSocket)."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'soutenanceai.settings')
django.setup()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application

from notation.routing import websocket_urlpatterns as notation_ws
from presentation.routing import websocket_urlpatterns as presentation_ws

# En développement (DEBUG=True), ASGIStaticFilesHandler sert les fichiers statiques
# directement sans avoir besoin de collectstatic ni de serveur web séparé.
# En production, retirer ce wrapper et configurer nginx/whitenoise à la place.
_http_app = get_asgi_application()
if settings.DEBUG:
    _http_app = ASGIStaticFilesHandler(_http_app)

application = ProtocolTypeRouter({
    'http': _http_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(notation_ws + presentation_ws)
        )
    ),
})
