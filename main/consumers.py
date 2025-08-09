from channels.generic.websocket import AsyncWebsocketConsumer
import json
import asyncio

class StatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.room_group_name = f'status_{self.task_id}'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # 실제로 파이썬 작업에서 send_progress를 호출!
    async def receive(self, text_data):
        # 필요시 클라이언트로부터 메시지 처리(거의 안 씀)
        pass

    async def send_progress(self, event):
        # 서버에서 이 함수 호출하면 클라이언트에 메시지 전송됨
        await self.send(text_data=json.dumps({
            'status': event['status'],
            'message': event.get('message', '')
        }))
