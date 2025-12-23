import os
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

SYSTEM_PROMPT = """
あなたは音声入力を解釈するAIです。
入力はすべてひらがなです。
ユーザーの意図を日本語で簡潔に説明してください。
"""

def analyze_with_llm(text: str):
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.2,
    )

    content = response.choices[0].message["content"]

    return {
        "normalized": text,
        "analysis": content,
    }
