# main.py — CLI entry point
#
# Run with: python main.py

import asyncio

from agent import run_agent
from database import init_db, get_patient, get_doctor
from tools import build_full_context
from mcp_client import call_tool


async def main() -> None:
    _banner()
    init_db()

    print("Choose role:")
    print("  1. Patient")
    print("  2. Doctor")
    role_choice = _prompt_int("\nEnter number: ", lo=1, hi=2)

    print()
    if role_choice == 1:
        await patient_flow()
    else:
        await doctor_flow()


# ── Patient flow ──────────────────────────────────────────────────────────────

async def patient_flow() -> None:
    patient_id = input("Your Patient ID (e.g. PT-00001): ").strip().upper()
    if not patient_id:
        print("Patient ID is required.")
        return

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

    print()
    symptoms = input("Describe your symptoms: ").strip()
    if not symptoms:
        print("No symptoms entered. Exiting.")
        return

    result = await run_agent(
        symptoms,
        patient_id=patient_id,
        patient_context=patient_context,
    )
    urgency = result["urgency"]
    doctors = result["doctors"]

    if not doctors:
        print("No matching doctors were found.")
        return

    print()
    print("-" * 55)
    print("Choose a doctor:")
    for i, doc in enumerate(doctors, 1):
        print(f"  {i}. {doc['name']} ({doc['specialty']})")

    doctor_choice = _prompt_int("\nEnter number: ", lo=1, hi=len(doctors))
    selected = doctors[doctor_choice - 1]
    print(f"\n  Selected: {selected['name']}")

    print()
    print("[7] ACT")
    slot_result = await call_tool("tool_get_slots", {
        "doctor_id": selected["id"],
        "urgency": urgency,
    })

    print("\n[8] OBSERVE")
    print(
        f"  Found {slot_result['total_free_found']} free slot(s) "
        f"within {slot_result['urgency_window_days']}-day window"
    )

    if not slot_result["slots"]:
        print(f"  No free slots for {selected['name']}. Try another doctor.")
        return

    print()
    print(f"Available slots for {selected['name']}:")
    for i, slot in enumerate(slot_result["slots"], 1):
        label = "tomorrow" if slot["days_away"] == 1 else f"in {slot['days_away']} days"
        print(f"  {i}. {slot['date']} at {slot['time']}  ({label})")

    slot_choice = _prompt_int("\nEnter slot number: ", lo=1, hi=len(slot_result["slots"]))
    chosen = slot_result["slots"][slot_choice - 1]

    print()
    print("[9] ACT")
    booking = await call_tool("tool_book_slot", {
        "doctor_id": selected["id"],
        "slot_key": chosen["slot_key"],
        "patient_id": patient_id,
        "symptoms": symptoms,
    })

    print("\n[10] OBSERVE")
    if not booking["success"]:
        print(f"  Booking failed: {booking['reason']}")
        return

    _print_patient_confirmation(patient_id, booking, chosen)


# ── Doctor flow ───────────────────────────────────────────────────────────────

async def doctor_flow() -> None:
    print("Doctor login uses the DOCTOR id tied to the doctor account.")
    print("Example: DOC-001")
    doctor_id = input("Your Doctor ID: ").strip().upper()

    if not doctor_id:
        print("Doctor User ID is required.")
        return

    doctor = get_doctor(doctor_id)
    if not doctor:
        print(f"  [DB] Doctor account '{doctor_id}' not found.")
        return

    print(
        f"\n  [DB] Found: {doctor['name']} | "
        f"{doctor['specialty']} | doctor_id={doctor['id']}"
    )

    while True:
        print()
        print("Doctor menu:")
        print("  1. View my appointments")
        print("  2. Create medical record")
        print("  3. Exit")

        choice = _prompt_int("\nEnter number: ", lo=1, hi=3)

        if choice == 1:
            result = await call_tool("tool_doctor_get_my_appointments", {
                "doctor_id": doctor_id,
            })
            _print_doctor_appointments(result)

        elif choice == 2:
            patient_id = input("Patient ID: ").strip().upper()
            symptoms = input("Symptoms: ").strip()
            symptom_count_raw = input("Symptom count (optional): ").strip()
            diagnosis = input("Diagnosis (optional): ").strip()
            appointment_id = input("Appointment ID (optional): ").strip().upper()

            symptom_count = int(symptom_count_raw) if symptom_count_raw.isdigit() else 0

            result = await call_tool("tool_doctor_create_medical_record", {
                "doctor_id": doctor_id,
                "patient_id": patient_id,
                "symptoms": symptoms,
                "symptom_count": symptom_count,
                "diagnosis": diagnosis,
                "appointment_id": appointment_id,
            })

            _print_medical_record_result(result)

        else:
            print("Exiting doctor menu.")
            return


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


def _print_patient_confirmation(patient_id: str, booking: dict, slot: dict) -> None:
    print()
    print("=" * 55)
    print("  APPOINTMENT CONFIRMED")
    print("=" * 55)
    print(f"  Patient ID : {patient_id}")
    if booking["patient_found_in_db"]:
        print(f"  Name       : {booking['patient_name']}")
    print(f"  Doctor     : {booking['doctor_name']}")
    print(f"  Specialty  : {booking['doctor_specialty']}")
    print(f"  Date       : {slot['date']}")
    print(f"  Time       : {slot['time']}")
    print(f"  Ref        : {booking['booking_ref']}")
    print(f"  Appt ID    : {booking['appointment_id']}")
    print("=" * 55)


def _print_doctor_appointments(result: dict) -> None:
    print()
    if not result["success"]:
        print(f"  Failed: {result['reason']}")
        return

    print("=" * 55)
    print(f"  APPOINTMENTS FOR {result['doctor_name']}")
    print("=" * 55)

    appointments = result.get("appointments", [])
    if not appointments:
        print("  No appointments found.")
        return

    for i, appt in enumerate(appointments, 1):
        print(f"  {i}. {appt['scheduled_at']} | {appt['patient_name']} "
              f"({appt['patient_id']}) | {appt['status']}")
        if appt.get("reason"):
            print(f"     Reason: {appt['reason']}")
        print(f"     Appointment ID: {appt['appointment_id']} | Ref: {appt['booking_ref']}")


def _print_medical_record_result(result: dict) -> None:
    print()
    if not result["success"]:
        print(f"  Failed: {result['reason']}")
        return

    print("=" * 55)
    print("  MEDICAL RECORD CREATED")
    print("=" * 55)
    print(f"  Record ID  : {result['record_id']}")
    print(f"  Doctor     : {result['doctor_name']} ({result['doctor_id']})")
    print(f"  Patient    : {result['patient_name']} ({result['patient_id']})")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())