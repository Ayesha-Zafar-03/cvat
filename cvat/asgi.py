# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cvat.settings.development")

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import cvat.apps.test.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            cvat.apps.test.routing.websocket_urlpatterns
        )
    ),
})