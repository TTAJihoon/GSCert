import sqlite3
import numpy as np
from pathlib import Path
from threading import Lock

BASE_DIR = Path(__file__).resolve().parents[3]
DB_PATH = BASE_DIR / "main" / "data" / "reference.db"
INDEX_PATH = BASE_DIR / "main" / "data" / "faiss_bge_m3_ko.idmap.index"
MODEL_NAME = "upskyy/bge-m3-korean"

_cache_lock = Lock()
_cached_index = None
_cached_index_mtime = None
_cached_model = None


class SimilarSearchDependencyError(RuntimeError):
    pass


def _import_faiss():
    try:
        import faiss
        return faiss
    except ImportError as exc:
        raise SimilarSearchDependencyError(
            "유사도 검색 패키지가 설치되지 않았습니다. requirements-search.txt를 설치하세요."
        ) from exc


def _import_sentence_transformer():
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer
    except ImportError as exc:
        raise SimilarSearchDependencyError(
            "임베딩 모델 패키지가 설치되지 않았습니다. requirements-search.txt를 설치하세요."
        ) from exc


def _get_index():
    global _cached_index, _cached_index_mtime

    if not INDEX_PATH.exists():
        raise SimilarSearchDependencyError(
            "유사도 검색 인덱스가 없습니다. manage.py embed_db main/data/reference.db 명령으로 인덱스를 생성하세요."
        )

    mtime = INDEX_PATH.stat().st_mtime
    with _cache_lock:
        if _cached_index is None or _cached_index_mtime != mtime:
            faiss = _import_faiss()
            _cached_index = faiss.read_index(str(INDEX_PATH))
            _cached_index_mtime = mtime
        return _cached_index


def _get_model():
    global _cached_model

    with _cache_lock:
        if _cached_model is None:
            SentenceTransformer = _import_sentence_transformer()
            _cached_model = SentenceTransformer(MODEL_NAME)
        return _cached_model

def select_data_from_db(indices):
    if not indices:
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    placeholders = ','.join('?' for _ in indices)
    query = f"SELECT * FROM sw_data WHERE 일련번호 IN ({placeholders})"
    cursor.execute(query, indices)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]

def compare_from_index(text, k=30):
    # 1) 인덱스 + 모델 로드
    index = _get_index()
    model = _get_model()

    # 2) 쿼리 임베딩
    query_vec = model.encode([text], normalize_embeddings=True).astype('float32')

    # 3) 검색 (D: 유사도(IP), L: 라벨=DB 일련번호)
    D, L = index.search(query_vec, k)

    labels = [int(x) for x in L[0] if x >= 0]
    sims   = [float(x) for x in D[0][:len(labels)]]

    # 4) DB 조회
    tables_unsorted = select_data_from_db(labels)
    id_to_table = {item['일련번호']: item for item in tables_unsorted}
    tables_in_rank = [id_to_table[i] for i in labels if i in id_to_table]

    # 5) similarity 부여
    for tbl, sim in zip(tables_in_rank, sims):
        tbl['similarity'] = sim

    # 6) 🔥 ID 내림차순 정렬
    tables_sorted = sorted(tables_in_rank, key=lambda x: int(x['일련번호']), reverse=True)
    similarities_sorted = [t['similarity'] for t in tables_sorted]

    return tables_sorted, similarities_sorted
