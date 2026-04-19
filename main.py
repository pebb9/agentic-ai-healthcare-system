# main.py — CLI entry point
#
# Run with: python main.py
#
# Patient flow: open-ended — MedGemma decides whether to book, cancel,
#               ask questions, or anything else.
# Doctor flow:  unchanged — hardcoded menu for appointments and records.

import asyncio

from agent    import run_agent
from database import init_db, get_patient
from tools    import build_full_context
from Validations import validate_patient_id, validate_symptoms, validate_advice, validate_booking



async def main() -> None:
    _banner()
    init_db()
    print("welcome!")
    await patient_flow()


# ── Patient flow ──────────────────────────────────────────────────────────────

async def patient_flow() -> None:
    while True:
        raw = input("Your Patient ID (e.g. PT-00001): ").strip().upper()
        ok, msg = validate_patient_id(raw)
        if ok:
            patient_id = raw
            break
        print(msg)

    patient = get_patient(patient_id)
    if not patient:
        print(f"  [DB] Patient '{patient_id}' not found.")
        return

    print(
        f"\n  [DB] Found: {patient['name']} | "
        f"{patient['age']} yrs | {patient['gender']}"
    )

    patient_context = build_full_context(patient_id)
    print(f"  [RAG] Context loaded — {len(patient_context)} chars")

    # Single open-ended prompt — the agent decides what to do from here.
    # Patient can say anything:
    #   "I have chest pain and need to see a doctor"
    #   "Cancel my booking BK-XXXXXXXX"
    #   "I need to reschedule, my ref is BK-XXXXXXXX"
    print()
    while True:
        user_message = input("How can we help you today? ").strip()
        ok, msg = validate_symptoms(user_message)
        if ok:
            break
        print(msg)

    result = await run_agent(
        user_message    = user_message,
        patient_id      = patient_id,
        patient_context = patient_context,
    )
 
    if result.get("type") == "advice":
        ok, msg = validate_advice(result.get("text", ""))
        print(msg if not ok else result["text"])
 
    elif result.get("type") == "booking":
        ok, msg = validate_booking(result)
        print(msg if not ok else f"Booking confirmed: {result['booking_ref']}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _banner() -> None:
    print()
    print("  " + "─" * 51)
    print("           HEALTHAGENT — Terminal Version         ")
    print("  " + "─" * 51)
    print()

if __name__ == "__main__":
    asyncio.run(main())