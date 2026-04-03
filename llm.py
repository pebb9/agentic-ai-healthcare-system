# llm.py — MedGemma client via Ollama

import json
import httpx

from config import MODEL, OLLAMA_URL

_GENERATE_URL = "http://localhost:11434/api/generate"
_TIMEOUT      = 120.0


async def ask_medgemma(prompt: str, patient_context: str = "") -> str:
    """
    Send a prompt to MedGemma via Ollama and return the response text.

    Falls back from /api/generate to /api/chat if the first attempt fails.
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

    Returns the parsed dict, or a fallback respond action on failure.
    """
    tool_descriptions = "\n".join(
        f'- {t["name"]}: {t["description"]}' for t in tools
    )

    history_text = ""
    for msg in messages:
        role    = msg["role"].upper()
        content = msg["content"]
        history_text += f"\n[{role}]: {content}"

    decision_prompt = f"""You are a medical appointment agent. Help patients book or cancel appointments by reasoning step by step and calling tools. If you are unsure of what the patient wants and the input is not clear, ask questions to get it clear.
When you have the symptoms and urgency, use the tool 'tool_get_advice' to get advice on what to do. If you need to find available slots for a doctor, use 'tool_get_slots' and show them to the patient. Based on the answer, use 'tool_book_slot' to book an appointment. That means tool_get_slots is not the final question. Ask the patient if he wants to book any of the available slots, and if yes, which one. Only then call tool_book_slot. 
After calling the tool tool_book_slot, please output the tool result and end the conversation with the patient by replying with a final response action.
Available tools:
{tool_descriptions}

Conversation so far:
{history_text}

Decide what to do next. Reply with ONLY valid JSON — no explanation, no markdown.

Options:
1. Call a tool:     {{"action": "call_tool", "tool": "<tool_name>", "args": {{...}}}}
2. Ask the patient: {{"action": "ask_user",  "message": "<your question>"}}
3. Final response:  {{"action": "respond",   "message": "<final message to patient>"}}

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