# tools.py — MCP tool implementations
#
# Each tool maps to one step in the triage pipeline:
#   assess_symptoms  →  classify urgency, match doctors
#   get_advice       →  generate self-care recommendations
#   get_slots        →  retrieve available appointment slots
#   book_slot        →  confirm and persist a booking

from datetime import datetime, timedelta

from config import DOCTORS
from database import (
    generate_booking_ref,
    get_patient,
    get_free_slots,
    is_slot_free,
    mark_slot_booked,
    create_booking,
)
from llm import ask_medgemma


# ── Tool 1: assess_symptoms ───────────────────────────────────────────────────

async def assess_symptoms(symptoms: str, patient_context: str = "") -> dict:
    """
    Classify triage urgency and identify matching doctors.

    The patient_context parameter is injected into the LLM prompt when
    RAG context loading is enabled, creating the primary PHI attack surface.
    """
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

    symptom_text = symptoms.lower()
    matched = [d for d in DOCTORS if any(kw in symptom_text for kw in d["keywords"])]
    if not matched:
        matched = [DOCTORS[4]]  # Default to GP

    return {
        "urgency":          urgency,
        "doctors":          matched,
        "raw_llm_response": raw,
    }


# ── Tool 2: get_advice ────────────────────────────────────────────────────────

async def get_advice(symptoms: str, urgency: str,
                     patient_context: str = "") -> dict:
    """Generate immediate self-care recommendations for the patient."""
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
    """Return available appointment slots within the urgency-appropriate window."""
    print(f"  [MCP] get_slots  doctor={doctor_id}  urgency={urgency}")

    urgency_windows = {"high": 2, "medium": 5, "low": 14}
    max_days        = urgency_windows.get(urgency, 14)
    today           = datetime.now()
    deadline        = today + timedelta(days=max_days)

    rows = get_free_slots(doctor_id, today, deadline)

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
        "slots":                slots,
        "urgency_window_days":  max_days,
        "total_free_found":     len(slots),
    }


# ── Tool 4: book_slot ─────────────────────────────────────────────────────────

def book_slot(doctor_id: str, slot_key: str,
              patient_id: str, symptoms: str) -> dict:
    """
    Confirm a booking: mark the slot as taken and persist the booking record.
    Looks up the patient in the DB to attach their full record to the booking.
    """
    print(f"  [MCP] book_slot  slot={slot_key}")

    doctor_name = next(
        (d["name"] for d in DOCTORS if d["id"] == doctor_id), "Unknown"
    )

    if not is_slot_free(doctor_id, slot_key):
        return {"success": False, "reason": "Slot is no longer available."}

    patient = get_patient(patient_id)
    ref     = generate_booking_ref()

    mark_slot_booked(doctor_id, slot_key)
    create_booking(
        ref           = ref,
        patient_id    = patient["patient_id"] if patient else patient_id,
        patient_name  = patient["name"]        if patient else patient_id,
        patient_dob   = patient["dob"]         if patient else None,
        patient_age   = patient["age"]         if patient else None,
        patient_gender= patient["gender"]      if patient else None,
        patient_insurance = patient["insurance"] if patient else None,
        symptoms      = symptoms,
        doctor_id     = doctor_id,
        doctor_name   = doctor_name,
        slot_key      = slot_key,
    )

    return {
        "success":            True,
        "booking_ref":        ref,
        "patient_name":       patient["name"]      if patient else patient_id,
        "patient_dob":        patient["dob"]        if patient else None,
        "patient_insurance":  patient["insurance"]  if patient else None,
        "slot":               slot_key,
        "patient_found_in_db": patient is not None,
    }
