from langchain_community.chat_models
import ChatOllama from langchain.schema
import HumanMessage
import pandas as pd
import os from pathlib
import Path

BASE_DIR = Path(file).resolve().parent.parent
file_path = BASE_DIR / "data" / "reference.xlsx"

#2. 엑셀 파일 읽기
df = pd.read_excel(file_path)

#3. 데이터가 너무 길면 모델이 못 읽기 때문에 상위 10개만 문자열로 추출
sample_data = df.head(10).to_string(index=False)

#4. 질문 정의 (테스트용)
user_question = "서울이라는 단어가 포함된 회사명을 알려줘."

#5. LLaMA 모델 연결
llm = ChatOllama(model="llama2")

#6. 모델에 보낼 전체 프롬프트 구성
prompt = f""" 다음은 reference.xlsx에서 가져온 일부 데이터입니다:
{sample_data}
사용자 질문: {user_question}
위 데이터를 참고하여 사용자의 질문에 대해 정확하고 간결하게 한국어로 답해주세요. """

#7. LangChain을 통해 LLaMA에 질문 전송
response = llm([HumanMessage(content=prompt)])

#8. 결과 출력
print("답변:") print(response.content)
