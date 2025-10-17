# --- Windows asyncio 정책: 반드시 Proactor 사용 (Playwright 서브프로세스 필요) ---
import sys, asyncio
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        # 일부 환경에서 이미 루프가 만들어진 뒤일 수도 있으나, ASGI import 초기에 실행되면 문제 없음
        pass
# -------------------------------------------------------------------------------

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from myproject import routing as project_routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(project_routing.websocket_urlpatterns)
    ),
})
