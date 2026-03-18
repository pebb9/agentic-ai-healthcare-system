# llm.py — MedGemma client via Ollama

import httpx

from config import MODEL, OLLAMA_URL

_GENERATE_URL = "http://localhost:11434/api/generate"
_TIMEOUT      = 120.0


async def ask_medgemma(prompt: str, patient_context: str = "") -> str:
    """
    Send a prompt to MedGemma via Ollama and return the response text.

    If patient_context is provided it is prepended to the prompt, making
    the patient record visible to the model (RAG-style injection).

    Falls back from the /api/generate endpoint to /api/chat if the first
    attempt fails, to handle different Ollama versions gracefully.
    """
    full_prompt = f"{patient_context}\n\n{prompt}" if patient_context else prompt

    attempts = [
        (
            _GENERATE_URL,
            {"model": MODEL, "prompt": full_prompt, "stream": False},
        ),
        (
            OLLAMA_URL,
            {
                "model":    MODEL,
                "messages": [{"role": "user", "content": full_prompt}],
                "stream":   False,
            },
        ),
    ]

    last_error = "no response"
    for url, payload in attempts:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                text = (
                    data.get("response")
                    or data.get("message", {}).get("content", "")
                )
                if text:
                    return text.strip()
        except Exception as exc:
            last_error = str(exc)

    return f"[MedGemma unavailable: {last_error}]"
