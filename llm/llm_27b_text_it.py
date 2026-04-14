import json
from pyexpat.errors import messages
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from threading import Lock

MEDGEMMA_MODEL = "google/medgemma-27b-text-it"

_tokenizer = None
_model = None
_lock = Lock()

def _load_model():
    """Load processor and model into GPU memory"""
    global _tokenizer, _model

    with _lock:
        if _model is not None:
            return      # model already loaded
        print("\nLoading MedGemma model...\n")

        _model = AutoModelForCausalLM.from_pretrained(
            MEDGEMMA_MODEL,
            dtype=torch.bfloat16, # recommended by Google
            device_map="auto"   # spreads across available GPUs
        )
        _tokenizer = AutoTokenizer.from_pretrained(
            MEDGEMMA_MODEL,
            use_fast="False"    # uses slower processor to achieve better results
        )
        _model.generation_config.pad_token_id = _tokenizer.eos_token_id     # silences the warning

        _model.eval()

        print("\nModel ready to receive user symptoms.\n\n")


async def ask_medgemma(prompt: str, patient_context: str = "") -> str:
    """
    Send a prompt to MedGemma agent and return the response text.

    If patient_context is provided it is prepended to the prompt, making
    the patient record visible to the model (RAG-style injection).
    """
    _load_model()

    print(f"\n\n[DEBUG] Patient context:\n{patient_context}\n\n")

    messages = [
        {
            "role": "system",
            "content": prompt
        },
        {
            "role": "user",
            "content": patient_context
        }
    ]

    try:
        inputs = _tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt"
        ).to(_model.device)

        input_len = inputs["input_ids"].shape[-1]
        print(f"\n\n[DEBUG] Input tokens: {input_len}\n")

        with torch.inference_mode():
            generation = _model.generate(
                **inputs,
                max_new_tokens=256,  # lower because of chatbot-style
                do_sample=True,
                temperature=0.3
            )
            generation = generation[0][input_len:]
        
        return _tokenizer.decode(generation, skip_special_tokens=True).strip()
    
    except Exception as exc:
        return f"\n\nMEDGEMMA UNAVAILABLE: {exc}"


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
        role = msg["role"].lower()
        content = msg["content"]

        if role == "user":
            role_label = "PATIENT"
        elif role == "assistant":
            role_label = "ASSISTANT"
        elif role == "tool":
            role_label = "TOOL"
        else:
            role_label = role.upper()

        history_text += f"\n[{role_label}]: {content}"

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

Decide what to do next. Reply with ONLY valid JSON — no explanation, no markdown, no extra text.

Options:
1. Call a tool:     {{"action": "call_tool", "tool": "<tool_name>", "args": {{...}}}}
2. Ask the patient: {{"action": "ask_user",  "message": "<your question>"}}
3. Final response:  {{"action": "respond",   "message": "<final message to patient>"}}

JSON:"""

    raw   = await ask_medgemma(decision_prompt, history_text)
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        decision = json.loads(clean)
        if "action" in decision:
            return decision
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: treat raw output as a final response
    return {"action": "respond", "message": raw}
