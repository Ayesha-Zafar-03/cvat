import json

from channels.generic.websocket import AsyncWebsocketConsumer


class ClassCountConsumer(AsyncWebsocketConsumer):
    """
    ws://<host>/ws/test/tasks/<task_id>/class-counts/
    Pushes live class-wise counts whenever annotations change.
    """

    async def connect(self):
        user = self.scope.get('user')
        if user is not None and not user.is_authenticated:
            await self.close(code=4401)
            return
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.group_name = f'class_counts_{self.task_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def class_count_update(self, event):
        await self.send(text_data=json.dumps(event["data"]))