from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/status/(?P<task_id>\w+)/$', consumers.StatusConsumer.as_asgi()),
]
