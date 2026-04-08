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

    decision_prompt = f"""You are a medical appointment agent. Help patients book or cancel appointments by reasoning step by step and calling tools. If you are unsure of what the patient wants and the input is not clear, ask questions to get it clear.

Before choosing your next action, check the conversation history and answer these questions:
- Have the patient's current symptoms been stated in a [PATIENT] message? If yes, do NOT ask for symptoms again.
- Has tool_assess_symptoms already returned a result? If yes, do NOT call it again. Move to the next step.
- Has tool_get_advice already returned a result? If yes, do NOT call it again.
- Has tool_get_slots already returned a result? If yes, do NOT call it again.
- Has the patient been asked whether they want to book or just receive advice? If not, ask that now.
- Has the patient chosen a slot? If not, do NOT call tool_book_slot.


1. If symptoms are vague, use ask_user to ask what symptoms the patient has RIGHT NOW.
2. Call tool_assess_symptoms once with the symptoms the patient described in this conversation.
3. Call tool_get_advice once to give self-care tips.
4. Use ask_user to ask the patient whether they want to book an appointment or just receive the advice.
5. If the patient wants to book: call tool_get_slots once, then use ask_user to show the slots and ask which one they want. Wait for their reply.
6. Only after the patient has chosen a slot, call tool_book_slot.
7. Use respond to confirm the booking. This ends the conversation.
8. If the patient only wants advice: use respond to deliver the advice and close the conversation.

Rules:
- NEVER call the same tool twice. Check the conversation history before calling any tool.
- NEVER ask the patient to describe their symptoms more than once. If the patient has described any symptoms at all in a [PATIENT] message, that is enough — call tool_assess_symptoms immediately.
- NEVER call tool_book_slot before the patient has chosen a slot in this conversation.
- NEVER assume the patient wants to book an appointment. Always ask first after assess_symptoms.
- NEVER use symptoms from the [SYSTEM] background record as the patient's current symptoms. Only use what the patient typed in [PATIENT] messages.
- Use ask_user when you still need a reply from the patient. Use respond ONLY for the truly final message — never put a question inside a respond message.
- ask_user is NOT a tool. Never put it in the "tool" field. It is an action type.
- The symptoms argument must always be a plain string (e.g. "headache, dizziness"), never a list.

Available tools:
{tool_descriptions}

Conversation so far:
{history_text}

Decide what to do next. Reply with ONLY valid JSON — no explanation, no markdown, no extra text.

Options:
1. Call a tool:     {{"action": "call_tool", "tool": "<tool_name>", "args": {{...}}}}
2. Ask the patient: {{"action": "ask_user",  "message": "<your question>"}}
3. Final response:  {{"action": "respond",   "message": "<final message to patient>"}}

JSON:"""

    raw   = await ask_medgemma(decision_prompt, )
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        decision = json.loads(clean)
        if "action" in decision:
            return decision
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: treat raw output as a final response
    return {"action": "respond", "message": raw}
