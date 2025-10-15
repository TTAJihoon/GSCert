from django.urls import path, re_path
from . import consumers

websocket_urlpatterns = [
    # task_id가 영숫자+하이픈(예: UUID)도 허용되게
    re_path(r"^ws/status/(?P<task_id>[\w-]+)/$", consumers.StatusConsumer.as_asgi()),
    # 또는 path 변환자 직접 정의해서 path()로 쓰는 방법도 있음
]
