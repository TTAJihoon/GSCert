# main/apps.py
from django.apps import AppConfig

class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        from main.utils import reload_reference  # 캐시 로직 있는 모듈 import
        reference_cache.reload_reference_dataframe()  # 서버 시작 시 1회만 실행
