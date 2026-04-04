# agent.py — True ReAct agent loop
#
# MedGemma is the ORCHESTRATOR — it decides every tool call, every
# clarifying question, and when the task is done. Python only executes
# what MedGemma decides.
#
# Supports in a single loop (no hardcoded branching):
#   - Booking a new appointment
#   - Cancelling an existing appointment by booking reference
#   - Asking the patient clarifying questions when needed
#   - Retrying a different doctor if no slots are found

from mcp_client import call_tool
from llm        import ask_medgemma_react

# ── Tool registry ─────────────────────────────────────────────────────────────
# Descriptions are what MedGemma reads when deciding what to do next.
# Keep them concise — they appear in every decision prompt.

TOOLS = [
    {
        "name":        "tool_assess_symptoms",
        "description": "Classify urgency (high/medium/low) and find matching doctors from symptoms. Call the tool like this: tool_assess_symptoms({'symptoms': '<symptom>'})",
        "args":        ["symptoms", "patient_id", "patient_context"],
    },
    {
        "name":        "tool_get_advice",
        "description": "Generate 3 immediate self-care tips based on symptoms and urgency level.",
        "args":        ["symptoms", "urgency", "patient_id", "patient_context"],
    },
    {
        "name":        "tool_get_slots",
        "description": "Get available appointment slots for a given doctor_id and urgency level.",
        "args":        ["doctor_id", "urgency"],
    },
    {
        "name":        "tool_book_slot",
        "description": "Book a specific slot. Requires doctor_id, slot_key, patient_id, and symptoms.",
        "args":        ["doctor_id", "slot_key", "patient_id", "symptoms"],
    },
    {
        "name":        "tool_cancel_appointment",
        "description": "Cancel an existing appointment using its booking reference (e.g. BK-XXXXXXXX).",
        "args":        ["booking_ref"],
    },
]

MAX_STEPS = 20  # Safety cap — prevents infinite loops


# ── Main agent loop ───────────────────────────────────────────────────────────

async def run_agent(user_message: str, patient_id: str = "",
                    patient_context: str = "") -> dict:
    """
    Run the agentic ReAct loop. MedGemma decides every step.

    Args:
        user_message:    The patient's opening message (symptoms, cancel request, etc.)
        patient_id:      Known patient ID — injected into context and tool calls.
        patient_context: RAG context block built from the patient's EHR record.

    Returns:
        dict with keys: final_message, steps_taken, history
    """
    _header("MEDGEMMA REACT AGENT")

    # ── Seed the conversation ─────────────────────────────────────────────
    system_context = "You are a medical appointment assistant."
    if patient_id:
        system_context += f" The patient's ID is {patient_id}."
    if patient_context:
        system_context += f"\n\nPatient record:\n{patient_context}"
        print(f"  [RAG] Context injected — {len(patient_context)} chars")

    history = [
        {"role": "system",  "content": system_context},
        {"role": "patient", "content": user_message},
    ]

    steps_taken   = 0
    final_message = ""
    print(f'\n  Patient: "{user_message}"')

    # ── ReAct loop ────────────────────────────────────────────────────────
    while steps_taken < MAX_STEPS:
        steps_taken += 1
        _step(steps_taken, "REASON → DECIDE")

        # Ask MedGemma: what should I do next?
        decision = await ask_medgemma_react(history, TOOLS)
        action   = decision.get("action")

        print(f"  MedGemma decided: {action}", end="")
        if action == "call_tool":
            print(f" → {decision.get('tool')}({decision.get('args', {})})")
        else:
            print()

        # ── call_tool ─────────────────────────────────────────────────
        if action == "call_tool":
            tool_name = decision.get("tool", "")
            tool_args = decision.get("args", {})
            known     = {t["name"] for t in TOOLS}

            if tool_name not in known:
                observation = f"Error: unknown tool '{tool_name}'. Available: {sorted(known)}"
                print(f"  [!] {observation}")
                history.append({"role": "observation", "content": observation})
                continue

            try:
                result      = await call_tool(tool_name, tool_args)
                observation = f"Tool '{tool_name}' returned: {result}"
                print(f"  [Tool result] {result}")
            except Exception as exc:
                observation = f"Tool '{tool_name}' failed with error: {exc}"
                print(f"  [Tool error] {exc}")

            history.append({"role": "observation", "content": observation})

            # Hint to MedGemma when no slots are found so it tries another doctor
            if (tool_name == "tool_get_slots"
                    and isinstance(result, dict)
                    and result.get("total_free_found", 0) == 0):
                history.append({
                    "role":    "observation",
                    "content": "No slots were available for that doctor. Consider trying a different doctor_id from the list returned by tool_assess_symptoms.",
                })

        # ── ask_user ──────────────────────────────────────────────────
        elif action == "ask_user":
            question = decision.get("message", "Could you provide more details?")
            print(f"\n  Agent: {question}")
            user_reply = input("  Patient: ").strip()
            history.append({"role": "agent",   "content": question})
            history.append({"role": "patient", "content": user_reply})

            # Count how many times the patient has already replied to an ask_user.
            # If they've replied at least once and the model keeps asking,
            # inject a hard instruction to stop clarifying and assess symptoms.
            patient_replies = sum(1 for m in history if m["role"] == "patient")
            if patient_replies >= 2:
                history.append({
                    "role":    "observation",
                    "content": "SYSTEM: The patient has already described their symptoms. Stop asking for more detail. Your next action MUST be call_tool with tool_assess_symptoms.",
                })

        # ── respond (send message, then continue) ────────────────────
        elif action == "respond":
            message = decision.get("message", "")
            _divider()
            print(f"\n  Agent: {message}\n")
            history.append({"role": "agent", "content": message})

            # Ask if the patient needs anything else
            follow_up = input("  Patient (or press Enter to finish): ").strip()
            if not follow_up:
                final_message = message
                break
            history.append({"role": "patient", "content": follow_up})

        # ── unknown fallback ──────────────────────────────────────────
        else:
            final_message = str(decision)
            _divider()
            print(f"\n  Agent: {final_message}\n")
            break

    if steps_taken >= MAX_STEPS:
        final_message = "Maximum reasoning steps reached. Please try again."
        print(f"\n  [!] {final_message}")

    return {
        "final_message": final_message,
        "steps_taken":   steps_taken,
        "history":       history,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _header(title: str) -> None:
    print()
    print("=" * 55)
    print(f"  {title}")
    print("=" * 55)

def _step(n: int, label: str) -> None:
    print(f"\n[{n}] {label}")

def _divider() -> None:
    print("=" * 55)


# Keep old names accessible so existing imports don't break
header  = _header
step    = _step
divider = _divider