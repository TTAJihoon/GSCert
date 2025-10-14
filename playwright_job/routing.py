from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # ws://서버주소/ws/run_job/ 경로로 웹소켓 연결이 오면
    # PlaywrightJobConsumer가 처리하도록 설정합니다.
    re_path(r'ws/run_job/$', consumers.PlaywrightJobConsumer.as_asgi()),
]
