from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path("ws/run_job/", consumers.PlaywrightJobConsumer.as_asgi()),
]
