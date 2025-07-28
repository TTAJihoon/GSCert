# 라이브러리 임포트
from fastapi import FastAPI, File, UploadFile
from sentence_transformers import SentenceTransformer
import fitz  # PyMuPDF
import docx
from pptx import Presentation
import os
import re
from tempfile import NamedTemporaryFile
import uvicorn

# FastAPI 인스턴스 생성
app = FastAPI()

# Sentence-BERT 모델 로딩 (한국어 전용 모델 사용)
model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')

# PDF에서 텍스트 추출 함수
def parse_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text("text")  # PDF 각 페이지에서 텍스트만 추출
    return text

# DOCX에서 텍스트 추출 함수
def parse_docx(file_path):
    doc = docx.Document(file_path)
    return "\n".join([para.text for para in doc.paragraphs])  # 문단 단위로 텍스트 추출

# PPTX에서 텍스트 추출 함수
def parse_pptx(file_path):
    prs = Presentation(file_path)
    text = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                # PPT의 각 슬라이드에서 텍스트 프레임 내의 모든 텍스트 추출
                text.extend([p.text for p in shape.text_frame.paragraphs])
    return "\n".join(text)

# 업로드된 파일 타입에 따라 적절한 파싱 함수 호출
def parse_file(file: UploadFile):
    # 업로드 파일을 임시 파일로 저장 (파일 형식 유지)
    with NamedTemporaryFile(delete=False, suffix='.' + file.filename.split('.')[-1]) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name  # 임시 파일 경로 저장

    try:
        # 파일 확장자 확인 후 적절한 파싱 함수 호출
        ext = file.filename.split('.')[-1].lower()
        if ext == 'pdf':
            return parse_pdf(tmp_path)
        elif ext == 'docx':
            return parse_docx(tmp_path)
        elif ext == 'pptx':
            return parse_pptx(tmp_path)
        else:
            return None
    finally:
        os.unlink(tmp_path)  # 임시 파일 삭제 (정리 필수)

# 텍스트 전처리 (불필요한 줄바꿈 및 공백 제거)
def preprocess_text(text):
    text = re.sub(r'\n+', '\n', text)  # 연속된 줄바꿈 → 단일 줄바꿈으로 축소
    text = re.sub(r'\s+', ' ', text)   # 연속된 공백 → 단일 공백으로 축소
    return text.strip()                # 앞뒤 공백 제거

# 대표 문장 추출 (Sentence-BERT 임베딩 사용)
def summarize_text(text):
    # 문장 분리 (문장 종결 부호 기준)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    if len(sentences) == 0:
        return "요약할 내용이 충분하지 않습니다."

    # 각 문장을 Sentence-BERT 임베딩으로 변환
    embeddings = model.encode(sentences)

    # 문서 전체 대표 벡터 (모든 문장 벡터의 평균)
    doc_embedding = embeddings.mean(axis=0)

    # 각 문장과 대표 벡터의 유사도(내적) 계산하여 가장 유사한 문장 선정
    scores = embeddings @ doc_embedding
    best_sentence = sentences[scores.argmax()]
    return best_sentence.strip()

# FastAPI 요약 API 엔드포인트 정의
@app.post("/summarize")
async def summarize_document(file: UploadFile = File(...)):
    # 업로드된 파일에서 텍스트 추출
    print(file)
    text = parse_file(file)

    # 지원하지 않는 형식이거나 내용 부족 시 에러 메시지 반환
    if text is None or len(text.strip()) < 10:
        return {"error": "지원되지 않는 파일 형식이거나 내용이 부족합니다."}

    # 텍스트 전처리 후 요약
    clean_text = preprocess_text(text)
    summary = summarize_text(clean_text)

    # 최종 요약 문장 반환
    print(summary)
    return {"summary": summary}

# FastAPI 서버 실행 (포트 8000)
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
