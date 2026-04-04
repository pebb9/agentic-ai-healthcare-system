# tools.py — MCP tool/service implementations

from datetime import datetime, timedelta

from config import DOCTORS, DISEASE_SPECIALTY
from database import (
    generate_booking_ref,
    get_patient, get_doctor, get_all_doctors,
    get_free_slots, is_slot_free, mark_slot_booked, mark_slot_free,
    create_appointment, get_appointment, get_appointment_by_ref,
    cancel_appointment_by_ref,
    get_appointments_for_doctor,
    get_medical_records_for_patient, create_medical_record,
)
from llm import ask_medgemma


# ── Symptom → specialty map (all 28 CSV symptoms covered) ────────────────────
_SYMPTOM_SPECIALTY: dict[str, list[str]] = {
    "chest pain":          ["Cardiology"],
    "shortness of breath": ["Cardiology", "Pulmonology"],
    "sweating":            ["Cardiology", "Endocrinology"],
    "palpitation":         ["Cardiology"],
    "headache":            ["Neurology", "ENT"],
    "dizziness":           ["Neurology", "ENT"],
    "blurred vision":      ["Neurology"],
    "tremors":             ["Neurology"],
    "rash":                ["Dermatology", "Immunology"],
    "swelling":            ["Dermatology", "Rheumatology", "Nephrology"],
    "anxiety":             ["Psychiatry"],
    "depression":          ["Psychiatry"],
    "insomnia":            ["Psychiatry"],
    "fever":               ["General Practice", "Infectious Disease"],
    "cough":               ["General Practice", "Pulmonology"],
    "fatigue":             ["General Practice", "Hematology", "Nephrology"],
    "nausea":              ["General Practice", "Gastroenterology"],
    "vomiting":            ["General Practice", "Gastroenterology"],
    "runny nose":          ["General Practice", "ENT", "Immunology"],
    "sore throat":         ["General Practice", "ENT"],
    "sneezing":            ["Immunology", "ENT"],
    "abdominal pain":      ["Gastroenterology"],
    "diarrhea":            ["Gastroenterology", "Infectious Disease"],
    "appetite loss":       ["Gastroenterology", "Endocrinology", "Hematology"],
    "weight gain":         ["Endocrinology"],
    "weight loss":         ["Endocrinology", "Gastroenterology", "Hematology"],
    "joint pain":          ["Rheumatology"],
    "muscle pain":         ["Rheumatology", "Infectious Disease"],
    "back pain":           ["Rheumatology", "Nephrology", "Hematology"],
}


def _match_doctors(symptoms: str, disease: str | None = None) -> list[dict]:
    """
    Match doctors using two strategies:
    1. Disease-based (precise) — uses DISEASE_SPECIALTY if patient has a known diagnosis.
    2. Symptom keyword scan    — maps symptom text to specialties via _SYMPTOM_SPECIALTY.
    Returns up to 3 unique doctors. Falls back to GP if nothing matches.
    """
    all_docs = {d["id"]: d for d in get_all_doctors()}
    specialties: list[str] = []

    # Strategy 1 — disease lookup
    if disease and disease in DISEASE_SPECIALTY:
        specialties.append(DISEASE_SPECIALTY[disease])

    # Strategy 2 — symptom keyword scan
    text = symptoms.lower()
    for keyword, specs in _SYMPTOM_SPECIALTY.items():
        if keyword in text:
            specialties.extend(specs)

    # Deduplicate, preserve order, cap at 3
    seen, unique = set(), []
    for s in specialties:
        if s not in seen:
            seen.add(s)
            unique.append(s)

    matched = []
    for spec in unique[:3]:
        doc = next((d for d in all_docs.values() if d["specialty"] == spec), None)
        if doc:
            matched.append({"id": doc["id"], "name": doc["name"], "specialty": doc["specialty"]})

    if not matched:
        gp = next((d for d in all_docs.values() if d["specialty"] == "General Practice"), None)
        if gp:
            matched = [{"id": gp["id"], "name": gp["name"], "specialty": gp["specialty"]}]

    return matched


def build_full_context(patient_id: str) -> str:
    """Build RAG context from the patient's DB record and medical history."""
    patient = get_patient(patient_id)
    records = get_medical_records_for_patient(patient_id, limit=5)

    parts = []
    if patient:
        parts.append(
            f"Patient profile: {patient['name']}, age {patient['age']}, "
            f"gender {patient['gender']}, insurance: {patient['insurance']}."
        )
        if patient["disease"]:
            parts.append(f"Known diagnosis: {patient['disease']}.")
        if patient["symptoms"]:
            parts.append(f"Recorded symptoms: {patient['symptoms']}.")

    if records:
        parts.append("Recent medical records:")
        for r in records:
            parts.append(
                f"- Symptoms: {r['symptoms'] or 'N/A'} | "
                f"Diagnosis: {r['diagnosis'] or 'N/A'} | "
                f"Date: {r['created_at']}"
            )

    return "\n".join(parts)


# ── Tool 1: assess_symptoms ───────────────────────────────────────────────────

async def assess_symptoms(symptoms: str, patient_id: str = "",
                           patient_context: str = "") -> dict:
    print("  [MCP] assess_symptoms")

    raw = await ask_medgemma(
        f"""A patient says: "{symptoms}"

Classify urgency as: high, medium, or low.
- high   = needs emergency care today
- medium = should see a doctor within a few days
- low    = routine appointment is fine

Reply with the urgency word first, then a brief explanation.
Suggest 1-3 doctor specialties suited to these symptoms.""",
        patient_context=patient_context,
    )

    lower = raw.lower()
    if   "high"   in lower: urgency = "high"
    elif "medium" in lower: urgency = "medium"
    else:                   urgency = "low"

    disease = None
    if patient_id:
        p = get_patient(patient_id)
        if p:
            disease = p["disease"]

    matched = _match_doctors(symptoms, disease=disease)

    return {"urgency": urgency, "doctors": matched, "raw_llm_response": raw}


# ── Tool 2: get_advice ────────────────────────────────────────────────────────

async def get_advice(symptoms: str, urgency: str,
                     patient_id: str = "", patient_context: str = "") -> dict:
    print("  [MCP] get_advice")

    advice = await ask_medgemma(
        f"""Patient symptoms: {symptoms}
Urgency: {urgency}

Give 3 things the patient can do RIGHT NOW to feel better.
One sentence each. No bullet points.""",
        patient_context=patient_context,
    )
    return {"advice": advice}


# ── Tool 3: get_slots ─────────────────────────────────────────────────────────

def get_slots(doctor_id: str, urgency: str) -> dict:
    print(f"  [MCP] get_slots  doctor={doctor_id}  urgency={urgency}")

    urgency_windows = {"high": 2, "medium": 5, "low": 14}
    max_days = urgency_windows.get(urgency, 14)
    today    = datetime.now()
    deadline = today + timedelta(days=max_days)

    rows  = get_free_slots(doctor_id, today, deadline)
    slots = []
    for row in rows:
        dt = datetime.strptime(row["slot_key"], "%Y-%m-%d %H:%M")
        slots.append({
            "slot_key":  row["slot_key"],
            "date":      dt.strftime("%A %d %B"),
            "time":      dt.strftime("%H:%M"),
            "days_away": (dt - today).days,
        })

    return {"slots": slots, "urgency_window_days": max_days, "total_free_found": len(slots)}


# ── Tool 4: book_slot ─────────────────────────────────────────────────────────

def book_slot(doctor_id: str, slot_key: str,
              patient_id: str, symptoms: str) -> dict:
    print(f"  [MCP] book_slot  slot={slot_key}")

    if not is_slot_free(doctor_id, slot_key):
        return {"success": False, "reason": "Slot is no longer available."}

    patient = get_patient(patient_id)
    doctor  = get_doctor(doctor_id)

    if not doctor:  return {"success": False, "reason": f"Doctor {doctor_id} not found."}
    if not patient: return {"success": False, "reason": f"Patient {patient_id} not found."}

    ref            = generate_booking_ref()
    appointment_id = f"APT-{ref[-8:]}"

    mark_slot_booked(doctor_id, slot_key)
    create_appointment(
        appointment_id=appointment_id, ref=ref,
        patient_id=patient_id, doctor_id=doctor_id,
        slot_key=slot_key, reason=symptoms, status="BOOKED",
    )

    return {
        "success":             True,
        "appointment_id":      appointment_id,
        "booking_ref":         ref,
        "patient_name":        patient["name"],
        "patient_id":          patient["id"],
        "doctor_name":         doctor["name"],
        "doctor_specialty":    doctor["specialty"],
        "slot":                slot_key,
        "patient_found_in_db": True,
    }


# ── Tool 5: cancel_appointment ────────────────────────────────────────────────

def cancel_appointment(booking_ref: str) -> dict:
    print(f"  [MCP] cancel_appointment  ref={booking_ref}")

    appointment = get_appointment_by_ref(booking_ref.strip())
    if not appointment:
        return {"success": False, "reason": f"No appointment found with reference '{booking_ref}'."}
    if appointment["status"] == "CANCELLED":
        return {"success": False, "reason": f"Appointment {booking_ref} is already cancelled."}

    cancel_appointment_by_ref(booking_ref.strip())
    mark_slot_free(appointment["doctor_id"], appointment["scheduled_at"])

    return {
        "success":        True,
        "booking_ref":    booking_ref,
        "appointment_id": appointment["id"],
        "patient_name":   appointment["patient_name"],
        "doctor_name":    appointment["doctor_name"],
        "slot":           appointment["scheduled_at"],
    }


# ── Doctor tools ──────────────────────────────────────────────────────────────

def doctor_get_my_appointments(doctor_id: str) -> dict:
    print(f"  [MCP] doctor_get_my_appointments  doctor={doctor_id}")

    doctor = get_doctor(doctor_id)
    if not doctor:
        return {"success": False, "reason": "Doctor not found."}

    items = []
    for a in get_appointments_for_doctor(doctor["id"]):
        items.append({
            "appointment_id": a["id"],
            "booking_ref":    a["booking_ref"],
            "patient_id":     a["patient_id"],
            "patient_name":   a["patient_name"],
            "scheduled_at":   a["scheduled_at"],
            "status":         a["status"],
            "reason":         a["reason"],
        })

    return {
        "success":      True,
        "doctor_id":    doctor["id"],
        "doctor_name":  doctor["name"],
        "specialty":    doctor["specialty"],
        "appointments": items,
    }


def doctor_create_medical_record(
    doctor_id: str, patient_id: str, symptoms: str,
    symptom_count: int | None = None,
    diagnosis: str | None = None,
    appointment_id: str | None = None,
) -> dict:
    print(f"  [MCP] doctor_create_medical_record  patient={patient_id}")

    doctor  = get_doctor(doctor_id)
    patient = get_patient(patient_id)

    if not doctor:  return {"success": False, "reason": "Doctor not found."}
    if not patient: return {"success": False, "reason": "Patient not found."}

    linked_id = appointment_id.upper() if appointment_id else None
    if linked_id:
        appt = get_appointment(linked_id)
        if not appt:
            return {"success": False, "reason": "Appointment not found."}
        if appt["doctor_id"] != doctor["id"]:
            return {"success": False, "reason": "Appointment does not belong to this doctor."}
        if appt["patient_id"] != patient["id"]:
            return {"success": False, "reason": "Appointment does not belong to this patient."}

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    record_id = f"MR-{patient['id'].split('-')[-1]}-{timestamp}"

    create_medical_record(
        record_id=record_id, patient_id=patient["id"],
        doctor_id=doctor["id"], symptoms=symptoms,
        symptom_count=symptom_count, diagnosis=diagnosis,
        appointment_id=linked_id,
    )

    return {
        "success":        True,
        "record_id":      record_id,
        "doctor_id":      doctor["id"],
        "doctor_name":    doctor["name"],
        "patient_id":     patient["id"],
        "patient_name":   patient["name"],
        "appointment_id": linked_id,
    }