import os
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.document_loaders.csv_loader import CSVLoader

def build_chroma_from_csv(csv_path):
    # 절대 경로로 chroma_db 경로 지정
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # main/
    chroma_path = os.path.join(base_dir, "data", "chroma_db")

    embedding = HuggingFaceEmbeddings(model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS")
    loader = CSVLoader(file_path=csv_path)
    docs = loader.load()
    
    db = Chroma.from_documents(documents=docs, embedding=embedding, persist_directory=chroma_path)
    db.persist()
    print(f"✅ Chroma 저장 완료: {chroma_path}")
