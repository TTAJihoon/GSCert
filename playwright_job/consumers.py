import asyncio
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .tasks import run_playwright_task # 4단계에서 만들 실제 작업 함수

# 최대 5개의 작업만 동시에 실행되도록 세마포어(Semaphore)를 설정합니다.
# 이 Consumer를 사용하는 모든 사용자가 이 세마포어를 공유합니다.
SEMAPHORE = asyncio.Semaphore(5)

class PlaywrightJobConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """웹소켓 연결이 처음 맺어질 때 호출됩니다."""
        await self.accept()
        print(f"WebSocket connected: {self.channel_name}")

    async def disconnect(self, close_code):
        """웹소켓 연결이 끊어질 때 호출됩니다."""
        print(f"WebSocket disconnected: {self.channel_name}")

    async def receive(self, text_data):
        """클라이언트로부터 메시지를 받았을 때 호출됩니다."""
        
        # 1. 동시 실행 개수 제어 (최대 5개)
        await self.send(text_data=json.dumps({
            'status': 'wait',
            'message': '서버에서 실행 가능한 작업 공간을 확인 중입니다...'
        }))

        async with SEMAPHORE:
            # 세마포어를 획득하면 (5개 중 자리가 나면) 아래 로직이 실행됩니다.
            try:
                await self.send(text_data=json.dumps({
                    'status': 'processing',
                    'message': '작업을 시작합니다. 잠시만 기다려주세요...'
                }))
                
                # 2. 실제 Playwright 작업 실행 (tasks.py에 위임)
                result = await run_playwright_task()

                # 3. 성공 결과 전송
                await self.send(text_data=json.dumps({
                    'status': 'success',
                    'url': result['url']
                }))

            except Exception as e:
                # 4. 실패 시 에러 메시지 전송
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': f"오류가 발생했습니다: {str(e)}"
                }))
