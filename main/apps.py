# main/apps.py
from django.apps import AppConfig

class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        """
        서버 구동 시 자동으로 실행됨.
        reference_embeddings.npy와 reference_descriptions.csv를 로드합니다.
        """
        print("[MainConfig] 앱이 준비되었습니다. 임베딩 캐시 로딩 시도 중...")
        try:
            from .embedding_pipeline import load_embeddings
            load_embeddings()
            print("[MainConfig] 임베딩 로딩 성공")
        except Exception as e:
            print(f"[MainConfig] 임베딩 로딩 실패: {e}")
