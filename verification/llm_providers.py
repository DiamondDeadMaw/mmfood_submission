from typing import Protocol

import config


class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...


class GeminiProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        import google.generativeai as genai

        genai.configure(api_key=api_key or config.GEMINI_API_KEY)
        self._model = genai.GenerativeModel(model or config.LLM_MODEL or "gemini-1.5-flash")

    def complete(self, prompt: str) -> str:
        response = self._model.generate_content(prompt)
        return response.text.strip()


class OpenAICompatProvider:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key or "sk-local", base_url=base_url)
        self._model = model or config.LLM_MODEL or "gpt-4o-mini"

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()


def get_llm_provider(provider: str | None = None) -> LLMProvider:
    provider = (provider or config.LLM_PROVIDER).strip().lower()

    if provider == "gemini":
        return GeminiProvider()
    if provider == "openai":
        return OpenAICompatProvider(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
    if provider == "local":
        return OpenAICompatProvider(api_key=config.OPENAI_API_KEY, base_url=config.LLM_BASE_URL)

    raise ValueError(f"Unknown LLM provider: {provider}")
