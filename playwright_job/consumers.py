import asyncio
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .tasks import run_playwright_task

SEMAPHORE = asyncio.Semaphore(5)

class PlaywrightJobConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        print(f"WebSocket connected: {self.channel_name}")

    async def disconnect(self, close_code):
        print(f"WebSocket disconnected: {self.channel_name}")

    async def receive(self, text_data):
        # 클라이언트가 보낸 JSON 문자열을 파싱합니다.
        data = json.loads(text_data)
        cert_date = data.get('인증일자')
        test_no = data.get('시험번호')

        if not cert_date or not test_no:
            await self.send(text_data=json.dumps({
                'status': 'error',
                'message': '인증일자 또는 시험번호 정보가 누락되었습니다.'
            }))
            return

        await self.send(text_data=json.dumps({
            'status': 'wait',
            'message': '서버의 다른 작업이 끝나기를 기다리는 중입니다...'
        }))

        async with SEMAPHORE:
            try:
                await self.send(text_data=json.dumps({
                    'status': 'processing',
                    'message': 'Playwright 작업을 시작합니다.\n잠시만 기다려주세요...'
                }))
                
                # tasks.py의 함수에 인자를 전달합니다.
                result = await run_playwright_task(cert_date=cert_date, test_no=test_no)

                await self.send(text_data=json.dumps({
                    'status': 'success',
                    'url': result['url']
                }))

            except Exception as e:
                await self.send(text_data=json.dumps({
                    'status': 'error',
                    'message': f"오류가 발생했습니다: {str(e)}"
                }))
