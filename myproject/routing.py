import logging; logging.getLogger(__name__).warning(">>> myproject.routing 로딩됨")

import main.routing
import playwright_job.routing

websocket_urlpatterns = (
    main.routing.websocket_urlpatterns
    + playwright_job.routing.websocket_urlpatterns
)
