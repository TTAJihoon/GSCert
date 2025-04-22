from django.shortcuts import render
from pathlib import Path
from langchain_community.document_loaders import UnstructuredExcelLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.chat_models import ChatOllama
from langchain.chains import RetrievalQA

BASE_DIR = Path(__file__).resolve().parent.parent
EXCEL_PATH = BASE_DIR / "myproject" / "data" / "reference.xlsx"
CHROMA_PATH = BASE_DIR / "chroma_db"

def rag_query(request):
    answer = None

    if request.method == "POST":
        question = request.POST.get("question", "")

        # 1. 엑셀 파일 로드
        loader = UnstructuredExcelLoader(str(EXCEL_PATH))
        documents = loader.load()

        # 2. 텍스트 분할
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = splitter.split_documents(documents)

        # 3. 임베딩 + 벡터스토어
        embedding = OllamaEmbeddings(model="llama2")
        vectordb = Chroma.from_documents(docs, embedding, persist_directory=str(CHROMA_PATH))
        vectordb.persist()

        # 4. 모델 연결
        llm = ChatOllama(model="llama2")
        qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=vectordb.as_retriever())

        # 5. 답변 생성
        answer = qa_chain.run(question)

    return render(request, "main/query.html", {"answer": answer})
