import json

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .auth import can_user_view_task


class ClassCountConsumer(AsyncWebsocketConsumer):
    """
    Live class-wise counts for a single task.

    ws://<host>/ws/test/tasks/<task_id>/class-counts/

    The server pushes a JSON payload ({task_id, class_counts, total_annotations})
    every time the task annotations change in the database.
    """

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)  # Unauthorized
            return

        self.task_id = self.scope["url_route"]["kwargs"]["task_id"]

        task_exists_and_allowed = await sync_to_async(can_user_view_task)(
            user, self.task_id
        )
        if not task_exists_and_allowed:
            await self.close(code=4403)  # Forbidden
            return

        self.group_name = f"class_counts_{self.task_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def class_count_update(self, event):
        await self.send(text_data=json.dumps(event["data"]))
