import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .apps import BROWSER_POOL  # Semaphore 대신 브라우저 풀을 가져옵니다.
from .tasks import run_playwright_task

class PlaywrightJobConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        data = json.loads(text_data)
        cert_date = data.get('인증일자')
        test_no = data.get('시험번호')

        if not cert_date or not test_no:
            # ... (오류 처리 부분은 기존과 동일) ...
            return

        await self.send(text_data=json.dumps({
            'status': 'wait',
            'message': '사용 가능한 브라우저를 기다리는 중입니다...'
        }))

        browser = None
        try:
            # 1. 브라우저 풀에서 쉬고 있는 브라우저를 하나 가져옵니다.
            #    만약 모두 사용 중이면, 여기서 반납될 때까지 자동으로 기다립니다.
            browser = await BROWSER_POOL.get()

            await self.send(text_data=json.dumps({
                'status': 'processing',
                'message': 'Playwright 작업을 시작합니다.\n잠시만 기다려주세요...'
            }))
            
            # 2. 가져온 브라우저와 함께 실제 작업을 수행합니다.
            result = await run_playwright_task(browser=browser, cert_date=cert_date, test_no=test_no)

            await self.send(text_data=json.dumps({
                'status': 'success',
                'url': result['url']
            }))

        except Exception as e:
            await self.send(text_data=json.dumps({
                'status': 'error',
                'message': f"오류가 발생했습니다: {str(e)}"
            }))
        finally:
            # 3. 작업이 성공하든 실패하든, 사용했던 브라우저를 반드시 풀에 반납합니다.
            if browser:
                await BROWSER_POOL.put(browser)
