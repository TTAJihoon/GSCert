import main.routing
import playwright_job.routing

websocket_urlpatterns = (
    main.routing.websocket_urlpatterns
    + playwright_job.routing.websocket_urlpatterns
)
