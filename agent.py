# agent.py — ReAct agent loop
#
# Orchestrates the triage pipeline in a Reason → Act → Observe cycle:
#   1. Reason   — log the incoming symptoms
#   2. Act      — call assess_symptoms tool
#   3. Observe  — log urgency and matched doctors
#   4. Act      — call get_advice tool
#   5. Observe  — log advice
#   6. Respond  — surface results to the caller

from tools import assess_symptoms, get_advice


async def run_agent(symptoms: str, patient_context: str = "") -> dict:
    """
    Run the triage ReAct loop and return the assessment result.

    Args:
        symptoms:        Free-text symptom description from the patient.
        patient_context: Optional RAG context block injected into LLM prompts.

    Returns:
        dict with keys: urgency, doctors, raw_llm_response, advice
    """
    _header("MEDGEMMA REACT AGENT")

    if patient_context:
        print(f"  [RAG] Context injected — {len(patient_context)} chars")

    # ── Step 1: Reason ────────────────────────────────────────────────────
    _step(1, "REASON")
    print(f'  Symptoms: "{symptoms}"')

    # ── Step 2: Act — assess symptoms ─────────────────────────────────────
    _step(2, "ACT")
    assessment = await assess_symptoms(symptoms, patient_context=patient_context)

    # ── Step 3: Observe ───────────────────────────────────────────────────
    _step(3, "OBSERVE")
    print(f"  Urgency        : {assessment['urgency'].upper()}")
    print(f"  Raw LLM output : {assessment['raw_llm_response']!r}")
    print(f"  Doctors        : {', '.join(d['name'] for d in assessment['doctors'])}")

    # ── Step 4: Act — get self-care advice ────────────────────────────────
    _step(4, "ACT")
    advice_result = await get_advice(
        symptoms,
        assessment["urgency"],
        patient_context=patient_context,
    )

    # ── Step 5: Observe ───────────────────────────────────────────────────
    _step(5, "OBSERVE")
    print(f"  Advice received — {len(advice_result['advice'])} chars")

    # ── Step 6: Respond ───────────────────────────────────────────────────
    _step(6, "RESPOND")
    _divider()

    urgency_labels = {
        "high":   "HIGH — showing slots within 2 days",
        "medium": "MEDIUM — showing slots within 5 days",
        "low":    "LOW — showing slots within 2 weeks",
    }
    print(f"  Urgency: {urgency_labels[assessment['urgency']]}")
    print()
    print("What you can do right now:")
    print(advice_result["advice"])
    print()
    print("Recommended doctors:")
    for i, doc in enumerate(assessment["doctors"], 1):
        print(f"  {i}. {doc['name']} — {doc['specialty']}")

    return {**assessment, "advice": advice_result["advice"]}


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
