from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/test/tasks/(?P<task_id>\d+)/class-counts/$', consumers.ClassCountConsumer.as_asgi()),
]