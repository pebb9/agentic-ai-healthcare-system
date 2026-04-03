# tools.py — MCP tool/service implementations

from datetime import datetime, timedelta

from database import (
    generate_booking_ref,
    get_patient,
    get_doctor,
    get_all_doctors,
    get_free_slots,
    is_slot_free,
    mark_slot_booked,
    create_appointment,
    get_medical_records_for_patient,
    get_appointments_for_doctor,
    create_medical_record,
    get_appointment,
    get_appointment_by_ref,
    get_connection,
)
from llm import ask_medgemma


# ── Helpers ───────────────────────────────────────────────────────────────────

def _match_doctors_by_symptoms(symptoms: str, doctors: list[dict]) -> list[dict]:
    """
    Fallback keyword matcher — maps symptom text to doctor specialties.
    """
    symptom_text = symptoms.lower()

    specialty_keywords = {
        "Cardiology":       ["chest", "heart", "palpitation", "blood pressure", "angina"],
        "Dermatology":      ["skin", "rash", "itch", "mole", "eczema", "dermatitis"],
        "Neurology":        ["headache", "migraine", "dizziness", "blurred vision", "seizure"],
        "General Practice": ["fever", "cough", "pain", "fatigue", "nausea"],
    }

    matched = []
    for d in doctors:
        specialty = d["specialty"]
        keywords  = specialty_keywords.get(specialty, [])
        if any(kw in symptom_text for kw in keywords):
            matched.append({"id": d["id"], "name": d["name"], "specialty": specialty})

    if not matched and doctors:
        gp     = next((d for d in doctors if d["specialty"] == "General Practice"), None)
        chosen = gp if gp else doctors[0]
        matched = [{"id": chosen["id"], "name": chosen["name"], "specialty": chosen["specialty"]}]

    return matched


def _build_patient_context(patient_id: str) -> str:
    records = get_medical_records_for_patient(patient_id, limit=5)
    if not records:
        return ""
    lines = []
    for r in records:
        lines.append(
            f"- Symptoms: {r['symptoms'] or 'N/A'} | "
            f"Diagnosis: {r['diagnosis'] or 'N/A'} | "
            f"Created: {r['created_at']}"
        )
    return "\n".join(lines)


def build_full_context(patient_id: str) -> str:
    patient = get_patient(patient_id)
    records = get_medical_records_for_patient(patient_id, limit=10)

    parts = []
    if patient:
        parts.append(
            f"Patient profile: {patient['name']}, age {patient['age']}, gender {patient['gender']}."
        )
    if records:
        parts.append("Medical history:")
        for r in records:
            parts.append(
                f"- Symptoms: {r['symptoms'] or 'N/A'} | "
                f"Diagnosis: {r['diagnosis'] or 'N/A'} | "
                f"Created: {r['created_at']}"
            )

    return "\n".join(parts)


# ── Tool 1: assess_symptoms ───────────────────────────────────────────────────

async def assess_symptoms(symptoms: str, patient_context: str = "") -> dict:
    print("  [MCP] assess_symptoms")

    raw = await ask_medgemma(
        f"""A patient says: "{symptoms}"

Classify urgency in: high, medium, or low. Also take the patient context into account if provided.
- high   = needs emergency care today
- medium = should see a doctor within a few days
- low    = routine appointment is fine

Reply in one word and also provide a brief explanation of which symptoms or context features led to that classification. Then suggest 1-3 doctor specialties that would be a good match for these symptoms.""",
        patient_context=patient_context,
    )

    lower = raw.lower()
    if   "high"   in lower: urgency = "high"
    elif "medium" in lower: urgency = "medium"
    else:                   urgency = "low"

    doctors = get_all_doctors()
    matched = _match_doctors_by_symptoms(symptoms, doctors)

    return {
        "urgency":          urgency,
        "doctors":          matched,
        "raw_llm_response": raw,
    }


# ── Tool 2: get_advice ────────────────────────────────────────────────────────

async def get_advice(symptoms: str, urgency: str, patient_context: str = "") -> dict:
    print("  [MCP] get_advice")

    advice = await ask_medgemma(
        f"""Patient symptoms: {symptoms}
Urgency: {urgency}

Give 3 things they can do RIGHT NOW to feel better. One sentence each. No bullet points.""",
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

    return {
        "slots":               slots,
        "urgency_window_days": max_days,
        "total_free_found":    len(slots),
    }


# ── Tool 4: book_slot ─────────────────────────────────────────────────────────

def book_slot(doctor_id: str, slot_key: str,
              patient_id: str, symptoms: str) -> dict:
    print(f"  [MCP] book_slot  slot={slot_key}")

    if not is_slot_free(doctor_id, slot_key):
        return {"success": False, "reason": "Slot is no longer available."}

    patient = get_patient(patient_id)
    doctor  = get_doctor(doctor_id)

    if not doctor:
        return {"success": False, "reason": "Doctor not found."}

    ref            = generate_booking_ref()
    appointment_id = f"APT-{ref[-8:]}"

    mark_slot_booked(doctor_id, slot_key)
    create_appointment(
        appointment_id = appointment_id,
        ref            = ref,
        patient_id     = patient["id"] if patient else patient_id,
        doctor_id      = doctor_id,
        slot_key       = slot_key,
        reason         = symptoms,
        status         = "BOOKED",
    )

    return {
        "success":             True,
        "appointment_id":      appointment_id,
        "booking_ref":         ref,
        "patient_name":        patient["name"] if patient else patient_id,
        "doctor_name":         doctor["name"],
        "doctor_specialty":    doctor["specialty"],
        "slot":                slot_key,
        "patient_found_in_db": patient is not None,
    }


# ── Tool 5: cancel_appointment ────────────────────────────────────────────────

def cancel_appointment(booking_ref: str) -> dict:
    """
    Cancel an existing appointment by booking reference.
    Sets appointment status to CANCELLED and frees the slot.
    """
    print(f"  [MCP] cancel_appointment  ref={booking_ref}")

    appointment = get_appointment_by_ref(booking_ref.strip())
    if not appointment:
        return {
            "success": False,
            "reason":  f"No appointment found with reference '{booking_ref}'.",
        }

    if appointment["status"] == "CANCELLED":
        return {
            "success": False,
            "reason":  f"Appointment {booking_ref} is already cancelled.",
        }

    conn = get_connection()
    conn.execute(
        "UPDATE appointments SET status = 'CANCELLED' WHERE booking_ref = ?",
        (booking_ref.strip(),),
    )
    # Free the slot back up
    conn.execute(
        "UPDATE slots SET status = 'free' WHERE doctor_id = ? AND slot_key = ?",
        (appointment["doctor_id"], appointment["scheduled_at"]),
    )
    conn.commit()
    conn.close()

    return {
        "success":      True,
        "booking_ref":  booking_ref,
        "appointment_id": appointment["id"],
        "patient_name": appointment["patient_name"],
        "doctor_name":  appointment["doctor_name"],
        "slot":         appointment["scheduled_at"],
    }


# ── Doctor services ───────────────────────────────────────────────────────────

def doctor_get_my_appointments(doctor_id: str) -> dict:
    print(f"  [MCP] doctor_get_my_appointments  doctor={doctor_id}")

    doctor = get_doctor(doctor_id)
    if not doctor:
        return {"success": False, "reason": "Doctor account not found."}

    appointments = get_appointments_for_doctor(doctor["id"])

    items = []
    for a in appointments:
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
    doctor_id: str,
    patient_id: str,
    symptoms: str,
    symptom_count: int | None = None,
    diagnosis: str | None = None,
    appointment_id: str | None = None,
) -> dict:
    print(f"  [MCP] doctor_create_medical_record  patient={patient_id}")

    doctor  = get_doctor(doctor_id)
    if not doctor:
        return {"success": False, "reason": "Doctor account not found."}

    patient = get_patient(patient_id)
    if not patient:
        return {"success": False, "reason": "Patient not found."}

    linked_appointment_id = appointment_id.upper() if appointment_id else None

    if linked_appointment_id:
        appointment = get_appointment(linked_appointment_id)
        if not appointment:
            return {"success": False, "reason": "Appointment not found."}
        if appointment["doctor_id"] != doctor["id"]:
            return {"success": False, "reason": "Appointment does not belong to this doctor."}
        if appointment["patient_id"] != patient["id"]:
            return {"success": False, "reason": "Appointment does not belong to this patient."}

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    record_id = f"MR-{patient['id'].split('-')[-1]}-{timestamp}"

    create_medical_record(
        record_id      = record_id,
        patient_id     = patient["id"],
        doctor_id      = doctor["id"],
        symptoms       = symptoms,
        symptom_count  = symptom_count,
        diagnosis      = diagnosis,
        appointment_id = linked_appointment_id,
    )

    return {
        "success":        True,
        "record_id":      record_id,
        "doctor_id":      doctor["id"],
        "doctor_name":    doctor["name"],
        "patient_id":     patient["id"],
        "patient_name":   patient["name"],
        "appointment_id": linked_appointment_id,
    }