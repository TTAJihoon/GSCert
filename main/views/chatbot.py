from ollama import chat

def run_ollama_model(q1, q2, q3, q4, model="gemma3"):
    prompt = f"{q1}\n{q2}\n{q3}\n{q4}"

    try:
        response = chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response['message']['content']
    except Exception as e:
        return f"Ollama 처리 중 오류 발생: {str(e)}"
