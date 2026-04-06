# main.py — CLI entry point
#
# Run with: python main.py
#
# Patient flow: open-ended — MedGemma decides whether to book, cancel,
#               ask questions, or anything else.
# Doctor flow:  unchanged — hardcoded menu for appointments and records.

import asyncio

from agent    import run_agent
from database import init_db, get_patient, get_doctor
from tools    import build_full_context
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

    # Single open-ended prompt — the agent decides what to do from here.
    # Patient can say anything:
    #   "I have chest pain and need to see a doctor"
    #   "Cancel my booking BK-XXXXXXXX"
    #   "I need to reschedule, my ref is BK-XXXXXXXX"
    print()
    user_message = input("How can we help you today? ").strip()
    if not user_message:
        print("Nothing entered. Exiting.")
        return

    await run_agent(
        user_message    = user_message,
        patient_id      = patient_id,
        patient_context = patient_context,
    )


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
            patient_id      = input("Patient ID: ").strip().upper()
            symptoms        = input("Symptoms: ").strip()
            symptom_count_r = input("Symptom count (optional): ").strip()
            diagnosis       = input("Diagnosis (optional): ").strip()
            appointment_id  = input("Appointment ID (optional): ").strip().upper()

            symptom_count = int(symptom_count_r) if symptom_count_r.isdigit() else 0

            result = await call_tool("tool_doctor_create_medical_record", {
                "doctor_id":      doctor_id,
                "patient_id":     patient_id,
                "symptoms":       symptoms,
                "symptom_count":  symptom_count,
                "diagnosis":      diagnosis,
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
        print(label, end="", flush=True)
        raw = input().strip()
        if raw.isdigit() and lo <= int(raw) <= hi:
            return int(raw)
        print(f"  Please enter a number between {lo} and {hi}.")


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