import numpy as np
from pathlib import Path
from threading import Lock

from main.models import SwData
from main.utils.cert_date import format_cert_date, parse_cert_date

from .history import _build_notes_buttons

BASE_DIR = Path(__file__).resolve().parents[3]
INDEX_PATH = BASE_DIR / "main" / "data" / "faiss_bge_m3_ko.idmap.index"
MODEL_NAME = "upskyy/bge-m3-korean"

_cache_lock = Lock()
_cached_index = None
_cached_index_mtime = None
_cached_model = None

_FIELD_TO_KR = {
    'serial_number': '일련번호',
    'cert_number': '인증번호',
    'cert_date': '인증일자',
    'company': '회사명',
    'product': '제품',
    'grade': '등급',
    'test_number': '시험번호',
    'sw_category': 'SW분류',
    'product_desc': '제품설명',
    'total_wd': '총WD',
    'renewal': '재계약',
    'notes': '특이사항',
    'date_range': '시작날짜종료날짜',
    'test_lab': '시험원',
    'start_date': '시작일자',
    'end_date': '종료일자',
    'recert_type': '재인증구분',
    'prev_cert_info': '기인증번호제품정보버전',
    'kolas': 'KOLAS',
}


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
            "유사도 검색 인덱스가 없습니다. manage.py embed_db 명령으로 인덱스를 생성하세요."
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

    qs = SwData.objects.using('reference').filter(serial_number__in=indices)
    rows = []
    for obj in qs.values():
        row = {
            _FIELD_TO_KR[key]: value
            for key, value in obj.items()
            if key in _FIELD_TO_KR
        }
        row['인증일자'] = format_cert_date(row.get('인증일자'))
        row['특이사항_버튼'] = _build_notes_buttons(row)
        rows.append(row)
    return rows


def _parse_cert_date(value):
    return parse_cert_date(value)


def compare_from_index(text, k=30):
    # 1) 인덱스 + 모델 로드
    index = _get_index()
    model = _get_model()

    # 2) 쿼리 임베딩
    query_vec = model.encode([text], normalize_embeddings=True).astype('float32')

    # 3) 검색 (D: 유사도(IP), L: 라벨=DB 일련번호)
    D, L = index.search(query_vec, k)

    ranked_pairs = [
        (int(label), float(score))
        for label, score in zip(L[0], D[0])
        if label >= 0
    ]
    labels = [label for label, _ in ranked_pairs]
    score_by_id = {label: score for label, score in ranked_pairs}

    # 4) DB 조회
    tables_unsorted = select_data_from_db(labels)
    id_to_table = {item['일련번호']: item for item in tables_unsorted}
    tables_in_rank = [id_to_table[i] for i in labels if i in id_to_table]

    # 5) similarity 부여
    for tbl in tables_in_rank:
        sim = score_by_id.get(int(tbl['일련번호']), 0.0)
        tbl['similarity'] = sim
        tbl['faiss_similarity'] = sim

    similarities = [t['similarity'] for t in tables_in_rank]

    return tables_in_rank, similarities


def compare_multiple_from_index(
    texts,
    k=30,
    cert_date_from=None,
    cert_date_to=None,
):
    """여러 검색 문장의 제품별 FAISS 유사도를 평균 내어 상위 후보를 반환한다."""
    normalized_texts = [
        str(text or "").strip()
        for text in texts
        if str(text or "").strip()
    ]
    if not normalized_texts:
        return [], []

    index = _get_index()
    model = _get_model()
    query_vecs = model.encode(
        normalized_texts,
        normalize_embeddings=True,
    ).astype("float32")

    # 모든 제품에 대해 각 문장의 점수를 얻은 뒤 평균한다. 일부 문장의 top-k에
    # 들지 않은 제품을 0점으로 취급하면 평균 순위가 왜곡되므로 전체 인덱스를 조회한다.
    search_count = int(index.ntotal)
    if search_count <= 0:
        return [], []

    distances, labels = index.search(query_vecs, search_count)
    scores_by_id = {}
    for query_index in range(len(normalized_texts)):
        for label, score in zip(labels[query_index], distances[query_index]):
            if label < 0:
                continue
            scores_by_id.setdefault(int(label), []).append(float(score))

    ranked = sorted(
        (
            (
                label,
                sum(scores) / len(normalized_texts),
                scores,
            )
            for label, scores in scores_by_id.items()
            if len(scores) == len(normalized_texts)
        ),
        key=lambda item: item[1],
        reverse=True,
    )

    ranked_labels = [label for label, _, _ in ranked]
    tables_unsorted = select_data_from_db(ranked_labels)
    id_to_table = {int(item["일련번호"]): item for item in tables_unsorted}

    rows = []
    for label, average_score, per_query_scores in ranked:
        source_row = id_to_table.get(label)
        if not source_row:
            continue
        cert_date = _parse_cert_date(source_row.get("인증일자"))
        if cert_date_from and (not cert_date or cert_date < cert_date_from):
            continue
        if cert_date_to and (not cert_date or cert_date > cert_date_to):
            continue
        row = dict(source_row)
        row["similarity"] = average_score
        row["faiss_similarity"] = average_score
        row["faiss_scores"] = per_query_scores
        rows.append(row)
        if len(rows) >= k:
            break

    return rows, [row["similarity"] for row in rows]
