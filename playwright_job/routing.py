import logging; logging.getLogger(__name__).warning(">>> playwright_job.routing 로딩됨")

from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path("ws/run_job/", consumers.PlaywrightJobConsumer.as_asgi()),
]
