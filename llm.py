# llm.py — MedGemma client via Ollama

import json
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


async def ask_medgemma_react(messages: list[dict], tools: list[dict]) -> dict:
    """
    Send the full conversation history to MedGemma and ask it to decide
    the next action in the ReAct loop.

    MedGemma must reply with ONLY a JSON object choosing one of:
      { "action": "call_tool", "tool": "<name>", "args": { ... } }
      { "action": "ask_user",  "message": "<question for patient>" }
      { "action": "respond",   "message": "<final answer to patient>" }

    Returns the parsed dict, or a fallback respond action on parse failure.
    """
    tool_descriptions = "\n".join(
        f'- {t["name"]}: {t["description"]}' for t in tools
    )

    history_text = ""
    for msg in messages:
        role    = msg["role"].upper()
        content = msg["content"]
        history_text += f"\n[{role}]: {content}"

    decision_prompt = f"""You are a medical appointment agent. Help patients book or cancel appointments by reasoning step by step and calling tools.

Available tools:
{tool_descriptions}

Conversation so far:
{history_text}

Decide what to do next. Reply with ONLY valid JSON — no explanation, no markdown, no extra text.

Options:
1. Call a tool:     {{"action": "call_tool", "tool": "<tool_name>", "args": {{...}}}}
2. Ask the patient: {{"action": "ask_user",  "message": "<your question>"}}
3. Final response:  {{"action": "respond",   "message": "<final message to patient>"}}

When you call the tool tool_book_slot, please always ask the patient if the proposed time works for them before confirming the booking. You can call the tool multiple times if needed to find a suitable slot.
JSON:"""

    raw   = await ask_medgemma(decision_prompt)
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        decision = json.loads(clean)
        if "action" in decision:
            return decision
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: treat raw output as a final response
    return {"action": "respond", "message": raw}