# similar_summary.py (Django 전용 버전)

# Django에서 필요한 import
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# 텍스트 추출 관련 라이브러리
import fitz  # PyMuPDF
import docx
from pptx import Presentation

# 문장 처리 및 Sentence-BERT
from sentence_transformers import SentenceTransformer
import os
import re
from tempfile import NamedTemporaryFile

# Sentence-BERT 모델 로딩 (한국어 모델)
model = SentenceTransformer('snunlp/KR-SBERT-V40K-klueNLI-augSTS')

# PDF 파일에서 텍스트 추출
def parse_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text("text")
    return text

# DOCX 파일에서 텍스트 추출
def parse_docx(file_path):
    doc = docx.Document(file_path)
    return "\n".join([para.text for para in doc.paragraphs])

# PPTX 파일에서 텍스트 추출
def parse_pptx(file_path):
    prs = Presentation(file_path)
    text = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                text.extend([p.text for p in shape.text_frame.paragraphs])
    return "\n".join(text)

# 파일 파싱 (Django UploadedFile 객체 활용)
def parse_file(uploaded_file):
    with NamedTemporaryFile(delete=False, suffix='.' + uploaded_file.name.split('.')[-1]) as tmp:
        for chunk in uploaded_file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        ext = uploaded_file.name.split('.')[-1].lower()
        if ext == 'pdf':
            return parse_pdf(tmp_path)
        elif ext == 'docx':
            return parse_docx(tmp_path)
        elif ext == 'pptx':
            return parse_pptx(tmp_path)
        else:
            return None
    finally:
        os.unlink(tmp_path)

# 텍스트 전처리 (공백 및 줄바꿈 제거)
def preprocess_text(text):
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# 대표 문장 추출 (Sentence-BERT 이용)
def summarize_text(text):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    with open("C:/Users/Administrator/Desktop/test.txt", "w", encoding="utf-8") as file:
        for sentence in sentences:
            file.write(sentence + "\n")
    print("파일 저장 완료!")

    if len(sentences) == 0:
        return "요약할 내용이 충분하지 않습니다."

    embeddings = model.encode(sentences)
    doc_embedding = embeddings.mean(axis=0)
    scores = embeddings @ doc_embedding
    best_sentence = sentences[scores.argmax()]
    return best_sentence.strip()

# Django 뷰 함수 (요약 API)
@csrf_exempt
def summarize_document(request):
    if request.method == 'POST':
        file_type = request.POST.get('fileType', '')  # dropdown 선택값
        uploaded_file = request.FILES.get('file')  # 파일 입력값
        manual_input = request.POST.get('manualInput', '').strip()  # textarea 입력값
        print(file_type, uploaded_file, manual_input)

        if uploaded_file:  # 자동 입력 탭의 파일 처리
            print("파일 확인 완료: ", uploaded_file)
            text = parse_file(uploaded_file)
        elif manual_input:  # 수동 입력 탭의 텍스트 처리
            print("입력 내용 확인 완료: ", manual_input)
            text = manual_input
        else:
            return JsonResponse({'response': "파일이나 제품 설명을 입력해주세요."})

        if text is None or len(text.strip()) < 10:
            return JsonResponse({'response': "내용이 부족하거나 지원되지 않는 형식입니다."})
            
        clean_text = preprocess_text(text)
        sentences = re.split(r'(?<=[.!?])\s+', clean_text)        
        return JsonResponse({'response': '\n'.join(sentences)})

    return JsonResponse({'response': "POST 메소드만 지원됩니다."})
