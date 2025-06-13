from ollama import generate

def run_ollama_model(q1, q2, q3, q4, model="gemma3"):
    prompt = f"{q1}\n{q2}\n{q3}\n{q4}"

    try:
        print("[DEBUG] prompt:", prompt)
        response = generate(
            model=model,
            prompt=prompt
        )
        print("[DEBUG] response:", response)
        return response['message']['content']
    except Exception as e:
        print("[ERROR]", e)
        return f"Ollama 처리 중 오류 발생: {str(e)}"
