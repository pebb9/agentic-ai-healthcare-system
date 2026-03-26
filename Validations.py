# Validations.py — input and output validation for the patient-facing CLI
#
# On failure, message is shown directly to the patient.

import re

# ── Input validators ──────────────────────────────────────────────────────────

def validate_patient_id(raw: str) -> tuple[bool, str]:
    """
    Require PT-XXXXX (exactly 5 digits). Empty input is not accepted.
    """
    if not raw:
        return False, (
            "  A patient ID is required. Please enter your ID (e.g. PT-00042),\n"
            "  or a new one to register (e.g. PT-99999)."
        )
    if re.fullmatch(r"PT-\d{5}", raw):
        return True, ""
    return False, (
        "  Invalid patient ID format. Expected PT-XXXXX (e.g. PT-00042)."
    )


def validate_symptoms(raw: str) -> tuple[bool, str]:
    """
    Symptoms must be at least 3 characters and must not contain
    obvious prompt injection patterns.
    """
    if not raw or len(raw.strip()) < 3:
        return False, "  Please describe your symptoms (at least a few words)."

    injection_patterns = [
        r"ignore (previous|all|prior) instructions",
        r"\[system\]",
        r"begin (system )?override",
        r"you are now",
        r"act as (if )?",
        r"disregard .{0,30} (instructions|role|prompt)",
    ]
    lower = raw.lower()
    for pattern in injection_patterns:
        if re.search(pattern, lower):
            return False, (
                "  Your input contains text that cannot be processed.\n"
                "  Please describe your symptoms in plain language."
            )

    return True, ""


# ── Output validators ─────────────────────────────────────────────────────────

def validate_advice(advice: str) -> tuple[bool, str]:
    """
    Ensure the advice text is real content and not an LLM error string.
    On failure, message is a safe fallback shown to the patient.
    """
    if not advice or len(advice.strip()) < 10:
        return False, (
            "No advice available at this time. "
            "Please consult a doctor directly."
        )

    error_patterns = [
        r"medgemma unavailable",
        r"ollama unavailable",
        r"\[agent error",
        r"error.*exception",
    ]
    lower = advice.lower()
    for pattern in error_patterns:
        if re.search(pattern, lower):
            return False, (
                "The medical advice service is temporarily unavailable.\n"
                "Please contact your doctor or call emergency services if urgent."
            )

    return True, ""


def validate_booking(booking: dict) -> tuple[bool, str]:
    """
    Ensure the booking confirmation contains a valid ref and slot key.
    """
    ref      = booking.get("booking_ref", "")
    slot_key = booking.get("slot", "")

    if not re.fullmatch(r"BK-[A-Z0-9]{6}", ref):
        return False, f"  Booking reference looks invalid: '{ref}'"

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", slot_key):
        return False, f"  Slot key looks invalid: '{slot_key}'"

    return True, ""