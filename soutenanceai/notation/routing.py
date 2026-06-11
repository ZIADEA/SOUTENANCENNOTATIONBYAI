from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/passage/(?P<passage_id>\d+)/$', consumers.LivePassageConsumer.as_asgi()),
    re_path(r'ws/passage/(?P<passage_id>\d+)/audio/$', consumers.AudioStreamConsumer.as_asgi()),
]
