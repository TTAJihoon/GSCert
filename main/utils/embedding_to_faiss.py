from pathlib import Path
import sqlite3

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


DEFAULT_INDEX_PATH = Path("main/data/faiss_bge_m3_ko.idmap.index")
MODEL_NAME = "upskyy/bge-m3-korean"


def fetch_texts_from_sqlite(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 일련번호, 제품설명
        FROM sw_data
        WHERE 시작일자 >= '2016-01-01'
          AND 제품설명 IS NOT NULL
          AND TRIM(제품설명) != ''
        ORDER BY 일련번호
    """)
    rows = cursor.fetchall()
    conn.close()

    ids = [row[0] for row in rows]
    texts = [row[1] for row in rows]
    return ids, texts


def _create_id_index(dim):
    return faiss.IndexIDMap2(faiss.IndexFlatIP(dim))


def _encode_texts(model, texts):
    return model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=True,
    ).astype("float32")


def _get_index_ids(index):
    if not hasattr(index, "id_map"):
        raise ValueError("기존 인덱스가 IndexIDMap2 형식이 아닙니다.")
    return {int(index_id) for index_id in faiss.vector_to_array(index.id_map)}


def _write_index(index, index_path):
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))


def _rebuild_index(model, ids, texts, index_path):
    if not texts:
        print("임베딩할 텍스트가 없습니다. FAISS 인덱스를 생성하지 않습니다.")
        return {
            "mode": "empty",
            "added": 0,
            "total": 0,
            "index_path": str(index_path),
        }

    embeddings = _encode_texts(model, texts)
    print("임베딩 완료된 벡터 형태:", embeddings.shape)

    index = _create_id_index(embeddings.shape[1])
    index.add_with_ids(embeddings, np.array(ids, dtype=np.int64))
    _write_index(index, index_path)

    print("FAISS 인덱스 전체 재생성 완료 (IndexIDMap2):", index.ntotal)
    return {
        "mode": "rebuild",
        "added": len(ids),
        "total": index.ntotal,
        "index_path": str(index_path),
    }


def build_faiss_from_db(db_path, index_path=DEFAULT_INDEX_PATH, force_rebuild=False):
    ids, texts = fetch_texts_from_sqlite(db_path)
    print(f"조회된 텍스트 개수: {len(texts)}")

    index_path = Path(index_path)
    model = None

    if force_rebuild or not index_path.exists():
        if not texts:
            return _rebuild_index(model, ids, texts, index_path)
        model = SentenceTransformer(MODEL_NAME)
        return _rebuild_index(model, ids, texts, index_path)

    try:
        index = faiss.read_index(str(index_path))
        existing_ids = _get_index_ids(index)
    except Exception as exc:
        print(f"기존 FAISS 인덱스를 증분 갱신할 수 없어 전체 재생성합니다: {exc}")
        model = SentenceTransformer(MODEL_NAME)
        return _rebuild_index(model, ids, texts, index_path)

    new_pairs = [
        (row_id, text)
        for row_id, text in zip(ids, texts)
        if int(row_id) not in existing_ids
    ]

    if not new_pairs:
        print(f"신규 데이터가 없습니다. 기존 FAISS 인덱스를 유지합니다: {index.ntotal}")
        return {
            "mode": "unchanged",
            "added": 0,
            "total": index.ntotal,
            "index_path": str(index_path),
        }

    new_ids = [row_id for row_id, _ in new_pairs]
    new_texts = [text for _, text in new_pairs]

    model = SentenceTransformer(MODEL_NAME)
    embeddings = _encode_texts(model, new_texts)

    if index.d != embeddings.shape[1]:
        print(
            "기존 FAISS 인덱스 차원이 현재 모델과 달라 전체 재생성합니다: "
            f"{index.d} != {embeddings.shape[1]}"
        )
        return _rebuild_index(model, ids, texts, index_path)

    index.add_with_ids(embeddings, np.array(new_ids, dtype=np.int64))
    _write_index(index, index_path)

    print(
        "FAISS 인덱스 증분 갱신 완료: "
        f"추가 {len(new_ids)}건, 전체 {index.ntotal}건"
    )
    return {
        "mode": "incremental",
        "added": len(new_ids),
        "total": index.ntotal,
        "index_path": str(index_path),
    }
