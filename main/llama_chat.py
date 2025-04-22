from langchain_community.chat_models import ChatOllama
from langchain.schema import HumanMessage

# 로컬 모델 이름 (ollama pull로 설치한 이름)
llm = ChatOllama(model="llama2")

# 테스트 메시지
response = llm([HumanMessage(content="대한민국의 수도는 어디야?")])
print(response.content)
