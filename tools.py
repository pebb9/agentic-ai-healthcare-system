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
)
from llm.llm_27b_text_it import ask_medgemma


# ── Helpers ───────────────────────────────────────────────────────────────────

def _match_doctors_by_symptoms(symptoms: str, doctors: list[dict]) -> list[dict]:
    """
    Very simple fallback matcher based on specialty keywords.
    Keeps the old rule-based spirit while doctor data now comes from DB.
    """
    symptom_text = symptoms.lower()

    specialty_keywords = {
        "Cardiology":  ["chest", "heart", "palpitation", "blood pressure", "angina"],
        "Dermatology": ["skin", "rash", "itch", "mole", "eczema", "dermatitis"],
        "Neurology":   ["headache", "migraine", "dizziness", "blurred vision", "seizure"],
        "General Practice": ["fever", "cough", "pain", "fatigue", "nausea"],
    }

    matched = []
    for d in doctors:
        specialty = d["specialty"]
        keywords = specialty_keywords.get(specialty, [])
        if any(kw in symptom_text for kw in keywords):
            matched.append({
                "id": d["id"],
                "name": d["name"],
                "specialty": specialty,
            })

    if not matched and doctors:
        # fallback to GP if present, otherwise first doctor
        gp = next((d for d in doctors if d["specialty"] == "General Practice"), None)
        chosen = gp if gp else doctors[0]
        matched = [{
            "id": chosen["id"],
            "name": chosen["name"],
            "specialty": chosen["specialty"],
        }]

    return matched


def _build_patient_context(patient_id: str) -> str:
    """
    Build lightweight patient context from medical records.
    """
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


# ── Tool 1: assess_symptoms ───────────────────────────────────────────────────

async def assess_symptoms(symptoms: str, patient_id: str | None = None,
                          patient_context: str = "") -> dict:
    """
    Classify triage urgency and identify matching doctors.

    If patient_id is given, we can enrich context from medical_records.
    """
    print("  [MCP] assess_symptoms")

    db_context = _build_patient_context(patient_id) if patient_id else ""
    full_context = "\n".join(part for part in [patient_context, db_context] if part)

    raw = await ask_medgemma(
        f"""A patient says: "{symptoms}"

Classify urgency in: high, medium, or low. Also take the patient context into account if provided.
- high   = needs emergency care today
- medium = should see a doctor within a few days
- low    = routine appointment is fine

Reply in one word and also provide a brief explanation of which symptoms or context features led to that classification. Then suggest 1-3 doctor specialties that would be a good match for these symptoms.""",
        patient_context=full_context,
    )

    lower = raw.lower()
    if "high" in lower:
        urgency = "high"
    elif "medium" in lower:
        urgency = "medium"
    else:
        urgency = "low"

    doctors = get_all_doctors()
    matched = _match_doctors_by_symptoms(symptoms, doctors)

    return {
        "urgency": urgency,
        "doctors": matched,
        "raw_llm_response": raw,
    }


# ── Tool 2: get_advice ────────────────────────────────────────────────────────

async def get_advice(symptoms: str, urgency: str,
                     patient_id: str | None = None,
                     patient_context: str = "") -> dict:
    """Generate immediate self-care recommendations for the patient."""
    print("  [MCP] get_advice")

    db_context = _build_patient_context(patient_id) if patient_id else ""
    full_context = "\n".join(part for part in [patient_context, db_context] if part)

    advice = await ask_medgemma(
        f"""Patient symptoms: {symptoms}
Urgency: {urgency}

Give 3 things they can do RIGHT NOW to feel better. One sentence each. No bullet points.""",
        patient_context=full_context,
    )

    return {"advice": advice}


# ── Tool 3: get_slots ─────────────────────────────────────────────────────────

def get_slots(doctor_id: str, urgency: str) -> dict:
    """Return available appointment slots within the urgency-appropriate window."""
    print(f"  [MCP] get_slots  doctor={doctor_id}  urgency={urgency}")

    urgency_windows = {"high": 2, "medium": 5, "low": 14}
    max_days = urgency_windows.get(urgency, 14)
    today = datetime.now()
    deadline = today + timedelta(days=max_days)

    rows = get_free_slots(doctor_id, today, deadline)

    slots = []
    for row in rows:
        dt = datetime.strptime(row["slot_key"], "%Y-%m-%d %H:%M")
        slots.append({
            "slot_key": row["slot_key"],
            "date": dt.strftime("%A %d %B"),
            "time": dt.strftime("%H:%M"),
            "days_away": (dt - today).days,
        })

    return {
        "slots": slots,
        "urgency_window_days": max_days,
        "total_free_found": len(slots),
    }


# ── Tool 4: book_slot ─────────────────────────────────────────────────────────

def book_slot(doctor_id: str, slot_key: str,
              patient_id: str, symptoms: str) -> dict:
    """
    Confirm a booking: mark the slot as taken and persist the appointment record.
    """
    print(f"  [MCP] book_slot  slot={slot_key}")

    if not is_slot_free(doctor_id, slot_key):
        return {"success": False, "reason": "Slot is no longer available."}

    patient = get_patient(patient_id)
    doctor = get_doctor(doctor_id)

    if not doctor:
        return {"success": False, "reason": "Doctor not found."}

    ref = generate_booking_ref()
    appointment_id = f"APT-{ref[-6:]}"

    mark_slot_booked(doctor_id, slot_key)
    create_appointment(
        appointment_id=appointment_id,
        ref=ref,
        patient_id=patient["id"] if patient else patient_id,
        doctor_id=doctor_id,
        slot_key=slot_key,
        reason=symptoms,
        status="BOOKED",
    )

    return {
        "success": True,
        "appointment_id": appointment_id,
        "booking_ref": ref,
        "patient_name": patient["name"] if patient else patient_id,
        "doctor_name": doctor["name"],
        "doctor_specialty": doctor["specialty"],
        "slot": slot_key,
        "patient_found_in_db": patient is not None,
    }