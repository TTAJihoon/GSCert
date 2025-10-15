from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import main.routing
import playwright_job.routing

application = ProtocolTypeRouter({
    "websocket": AuthMiddlewareStack(
        URLRouter(
            main.routing.websocket_urlpatterns
            + playwright_job.routing.websocket_urlpatterns
        )
    ),
    # (http는 Django가 처리)
})
