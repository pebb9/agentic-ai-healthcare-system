# tools.py — MCP tool/service implementations

from datetime import datetime, timedelta

from config import DISEASE_SPECIALTY
from database import (
    generate_booking_ref,
    get_patient, get_doctor, get_all_doctors,
    get_free_slots, is_slot_free, mark_slot_booked, mark_slot_free,
    create_appointment, get_appointment_by_ref,
    cancel_appointment_by_ref,
    get_appointments_for_patient
)
from llm.llm_27b_text_it import ask_medgemma
# This is for local API runs.
# from llm.llm_API import ask_medgemma


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
    """Build RAG context from the patient's DB record """
    patient = get_patient(patient_id)

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

    return "\n".join(parts)


# ── Tool 1: assess_symptoms ───────────────────────────────────────────────────

async def assess_symptoms(symptoms: str, patient_id: str = "",
                           patient_context: str = "") -> dict:
    print("  [MCP] assess_symptoms")

    raw = await ask_medgemma(
        f"""A patient says: "{symptoms}"

Classify urgency as: high, medium, or low.
- high   = Symptoms indicate potentially severe or dangerous conditions and require immediate medical attention or evaluation within 24 hours.
- medium = Symptoms are not immediately dangerous, but should be evaluated by a doctor within 1–2 weeks to avoid complications or long-term effects.
- low    = Symptoms are mild, stable, and typically manageable through self-care.

Critical symptoms guidance:
Chest pain, breathing problems, fainting, and stroke-like symptoms may indicate dangerous conditions,
but should not automatically be classified as high.

Classify as high when symptoms are:
- severe
- disabling
- combined with multiple dangerous symptoms

Examples of High:
- Chest pain
- shortness of breath
- stroke-like symptoms
- coughing blood
- blue lips
- severe bleeding

Reply using exactly this structure:

Urgency: <high|medium|low>
Reason: <explanation>
Specialties:
- <specialty 1>
- <specialty 2>
- <specialty 3>

Do not use markdown.""",
        patient_context,
    )

    lower = raw.lower()
    urgency = "low"

    for line in lower.splitlines():
        line = line.strip()

        if line.startswith("urgency:"):
            if "high" in line:
                urgency = "high"
            elif "medium" in line:
                urgency = "medium"
            elif "low" in line:
                urgency = "low"

            break

    disease = None
    if patient_id:
        p = get_patient(patient_id)
        if p:
            disease = p["disease"]

    try:
        matched = _match_doctors(symptoms, disease=disease)
    except Exception as exc:
        print(f" [MCP] doctor matching skipped: {exc}")
        matched = []

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
        patient_context,
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

# ── Tool 6: get patient appointments ────────────────────────────────────────────────
def get_appointment_history(patient_id: str) -> dict:
    print(f"  [MCP] get_appointment_history  patient={patient_id}")

    patient = get_patient(patient_id)
    if not patient:
        return {"success": False, "reason": "Patient not found."}

    appointments = get_appointments_for_patient(patient_id, limit=10)
    if not appointments:
        return {"success": True, "patient_name": patient["name"], "appointments": [], "message": "No appointments found."}

    history = []
    for a in appointments:
        history.append({
            "date":      a["scheduled_at"],
            "doctor":    a["doctor_name"],
            "specialty": a["specialty"],
            "reason":    a["reason"],
            "status":    a["status"],
            "ref":       a["booking_ref"],
        })

    return {
        "success":      True,
        "patient_name": patient["name"],
        "appointments": history,
    }