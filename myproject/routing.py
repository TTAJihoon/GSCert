from channels.routing import URLRouter
from django.urls import path
import main.routing
import playwright_job.routing

# 'websocket_urlpatterns' 이름으로 합쳐서 export
websocket_urlpatterns = (
    main.routing.websocket_urlpatterns
    + playwright_job.routing.websocket_urlpatterns
)
