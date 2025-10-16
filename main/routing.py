from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # task_id에 하이픈(예: UUID)도 허용하려면 \w -> [\w-]
    re_path(r"^ws/status/(?P<task_id>[\w-]+)/$", consumers.StatusConsumer.as_asgi()),
]
