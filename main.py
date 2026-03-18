# main.py — CLI entry point
#
# Run with:  python main.py
# Requires:  pip install httpx
#            Ollama running with alibayram/medgemma:4b pulled
#            Healthcare.csv in the same folder

import asyncio

from agent    import run_agent
from database import init_db, get_patient, create_patient
from rag      import build_full_context
from tools    import get_slots, book_slot


async def main() -> None:
    _banner()
    init_db()

    # ── Identify patient ──────────────────────────────────────────────────
    print()
    patient_id = input("Your Patient ID (e.g. PT-00042, or press Enter to skip): ").strip().upper()

    patient_context = ""
    if patient_id:
        patient = get_patient(patient_id)

        if patient:
            print(f"\n  [DB] Found: {patient['name']} | {patient['age']} yrs, "
                  f"{patient['gender']} | {patient['disease']}")
            # Build RAG context: own record + nearby patients
            patient_context = build_full_context(patient_id)
            print(f"  [RAG] Context loaded — {len(patient_context)} chars "
                  f"(own record + 3 nearby)")
        else:
            print(f"  [DB] Patient '{patient_id}' not found — registering.")
            name    = input("  Full name              : ").strip() or "Anonymous"
            age_str = input("  Age                    : ").strip()
            age     = int(age_str) if age_str.isdigit() else 0
            gender  = input("  Gender (Male/Female/Other): ").strip() or "Other"
            create_patient(patient_id, name, age, gender, symptoms="")
            print(f"  [DB] Registered as {patient_id}.")

    # ── Symptom triage ────────────────────────────────────────────────────
    print()
    symptoms = input("Describe your symptoms: ").strip()
    if not symptoms:
        print("No symptoms entered. Exiting.")
        return

    result  = await run_agent(symptoms, patient_context=patient_context)
    urgency = result["urgency"]
    doctors = result["doctors"]

    # ── Doctor selection ──────────────────────────────────────────────────
    print()
    print("-" * 55)
    print("Choose a doctor:")
    for i, doc in enumerate(doctors, 1):
        print(f"  {i}. {doc['name']} ({doc['specialty']})")

    doctor_choice = _prompt_int("\nEnter number: ", lo=1, hi=len(doctors))
    selected      = doctors[doctor_choice - 1]
    print(f"\n  Selected: {selected['name']}")

    # ── Slot selection ────────────────────────────────────────────────────
    print()
    print(f"[7] ACT")
    slot_result = get_slots(selected["id"], urgency)

    print(f"\n[8] OBSERVE")
    print(f"  Found {slot_result['total_free_found']} free slot(s) "
          f"within {slot_result['urgency_window_days']}-day window")

    if not slot_result["slots"]:
        print(f"  No free slots for {selected['name']}. Try another doctor.")
        return

    print()
    print(f"Available slots for {selected['name']}:")
    for i, slot in enumerate(slot_result["slots"], 1):
        label = "tomorrow" if slot["days_away"] == 1 else f"in {slot['days_away']} days"
        print(f"  {i}. {slot['date']} at {slot['time']}  ({label})")

    slot_choice = _prompt_int("\nEnter slot number: ", lo=1, hi=len(slot_result["slots"]))
    chosen      = slot_result["slots"][slot_choice - 1]

    # ── Booking ───────────────────────────────────────────────────────────
    print()
    print("[9] ACT")
    booking = book_slot(selected["id"], chosen["slot_key"],
                        patient_id or "UNKNOWN", symptoms)

    print("\n[10] OBSERVE")
    if not booking["success"]:
        print(f"  Booking failed: {booking['reason']}")
        return

    _print_confirmation(patient_id, booking, selected, chosen)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _banner() -> None:
    print()
    print("  " + "─" * 51)
    print("           HEALTHAGENT — Terminal Version         ")
    print("  " + "─" * 51)
    print()


def _prompt_int(label: str, lo: int, hi: int) -> int:
    while True:
        raw = input(label).strip()
        if raw.isdigit() and lo <= int(raw) <= hi:
            return int(raw)
        print(f"  Please enter a number between {lo} and {hi}.")


def _print_confirmation(patient_id: str, booking: dict,
                         doctor: dict, slot: dict) -> None:
    print()
    print("=" * 55)
    print("  BOOKING CONFIRMED  (saved to calendar.db)")
    print("=" * 55)
    print(f"  Patient ID : {patient_id or 'UNKNOWN'}")
    if booking["patient_found_in_db"]:
        print(f"  Name       : {booking['patient_name']}")
        print(f"  DOB        : {booking['patient_dob']}")
        print(f"  Insurance  : {booking['patient_insurance']}")
    print(f"  Doctor     : {doctor['name']}")
    print(f"  Specialty  : {doctor['specialty']}")
    print(f"  Date       : {slot['date']}")
    print(f"  Time       : {slot['time']}")
    print(f"  Ref        : {booking['booking_ref']}")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
