# Django에서 필요한 import
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from tempfile import NamedTemporaryFile

# 텍스트 추출 관련 라이브러리
import fitz  # PyMuPDF
from pptx import Presentation

import os
import re
from .similar_GPT import run_openai_GPT
from .similar_compare import compare_from_index

# PDF 파일에서 텍스트 추출
def parse_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text("text")
    return text

# DOCX 파일에서 텍스트 추출
def parse_docx(file_path):
    from zipfile import ZipFile
    from lxml import etree, objectify

    WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with ZipFile(file_path) as z:
        xml = z.read("word/document.xml")
    root = objectify.fromstring(xml)

    text_blocks = []

    for child in root.body.iterchildren():
        tag = child.tag.replace(WORD_NS, "")
        if tag == "p":  # 문단
            p_text = " ".join(t.text for t in child.iter(tag=WORD_NS+"t") if t.text)
            if p_text.strip():
                text_blocks.append(p_text.strip())
        elif tag == "tbl":  # 표
            for row in child.iter(tag=WORD_NS+"tr"):
                cells = []
                for tc in row.iter(tag=WORD_NS+"tc"):
                    # 세로 병합(vMerge) 셀 'continue'는 skip
                    tcPr = tc.tcPr if hasattr(tc, 'tcPr') else None
                    vmerge = None
                    if tcPr is not None and hasattr(tcPr, 'vMerge'):
                        vmerge = getattr(tcPr.vMerge, "val", None)
                        if vmerge is None or vmerge == "continue":
                            continue  # 병합된 셀은 건너뜀
                    cell_text = " ".join(t.text for t in tc.iter(tag=WORD_NS+"t") if t.text)
                    if cell_text.strip():
                        cells.append(cell_text.strip())
                if cells:
                    text_blocks.append(" | ".join(cells))

    txt = "\n".join(text_blocks)
    txt = re.sub(r'(\n\s*){2,}', '\n', txt)
    return txt.strip()

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
            if text is None or len(text.strip()) < 10:
                return JsonResponse({'response': "내용이 부족하거나 지원되지 않는 형식입니다."})
        elif manual_input:  # 수동 입력 탭의 텍스트 처리
            print("입력 내용 확인 완료: ", manual_input)
            text = manual_input
            
        clean_text = preprocess_text(text)
        sentences = re.split(r'(?<=[.!?])\s+', clean_text)

        summary_text = run_openai_GPT(sentences)
        compare_result = compare_from_index(summary_text)
        sentences = [
            ', '.join([f"{key}: {value}" for key, value in row.items()])
            for row in compare_result
        ]
        
        return JsonResponse({'response': '\n'.join(sentences)})

    return JsonResponse({'response': "POST 메소드만 지원됩니다."})
