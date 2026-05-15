# mcp_server.py
# Run with:  python mcp_server.py
# Listens on: http://127.0.0.1:8000/mcp

import json
import sys
import time

from mcp.server.fastmcp import FastMCP

from llm.llm_27b_text_it import _load_model, ask_medgemma_react as _ask_medgemma_react
#This is for local API runs.
# from llm.llm_API import ask_medgemma_react as _ask_medgemma_react

from tools import (
    assess_symptoms,
    get_advice,
    get_slots,
    book_slot,
    cancel_appointment,
    get_appointment_history,
)
from mcp_logger import log_tool_call, log_tool_result

mcp = FastMCP("healthagent", host="127.0.0.1", port=8000)


# ── Tool 0: react_decide ───────────────────────────────────────────────────
# ReAct brain (called by agent.py instead of importing llm directly)
@mcp.tool()
async def tool_react_decide(
    messages_json: str,     # conversation history
    tools_json: str     # available tools
) -> str:
    messages = json.loads(messages_json)
    tools = json.loads(tools_json)
    decision = await _ask_medgemma_react(messages, tools)
    return json.dumps(decision)


# ── Tool 1: assess_symptoms ───────────────────────────────────────────────────

@mcp.tool()
async def tool_assess_symptoms(
    symptoms: str,
    patient_id: str = "",
    patient_context: str = "",
) -> str:
    user_id = f"USER-{patient_id}" if patient_id else None
    call_id = log_tool_call(
        tool_name  = "tool_assess_symptoms",
        arguments  = {"symptoms": symptoms, "patient_id": patient_id, "patient_context": patient_context},
        user_id    = user_id,
        patient_id = patient_id or None,
    )
    t0 = time.perf_counter()
    try:
        result = await assess_symptoms(symptoms, patient_id=patient_id, patient_context=patient_context) #added patient id because it was missing.
        log_tool_result(call_id=call_id, tool_name="tool_assess_symptoms", result=result, success=True, duration_ms=(time.perf_counter()-t0)*1000)
        return json.dumps(result)
    except Exception as exc:
        log_tool_result(call_id=call_id, tool_name="tool_assess_symptoms", result={}, success=False, error=str(exc))
        raise


# ── Tool 2: get_advice ────────────────────────────────────────────────────────

@mcp.tool()
async def tool_get_advice(
    symptoms: str,
    urgency: str,
    patient_id: str = "",
    patient_context: str = "",
) -> str:
    user_id = f"USER-{patient_id}" if patient_id else None
    call_id = log_tool_call(
        tool_name  = "tool_get_advice",
        arguments  = {"symptoms": symptoms, "urgency": urgency, "patient_id": patient_id, "patient_context": patient_context},
        user_id    = user_id,
        patient_id = patient_id or None,
    )
    t0 = time.perf_counter()
    try:
        result = await get_advice(symptoms, urgency, patient_context=patient_context)
        log_tool_result(call_id=call_id, tool_name="tool_get_advice", result=result, success=True, duration_ms=(time.perf_counter()-t0)*1000)
        return json.dumps(result)
    except Exception as exc:
        log_tool_result(call_id=call_id, tool_name="tool_get_advice", result={}, success=False, error=str(exc))
        raise


# ── Tool 3: get_slots ─────────────────────────────────────────────────────────

@mcp.tool()
def tool_get_slots(doctor_id: str, urgency: str) -> str:
    call_id = log_tool_call(
        tool_name = "tool_get_slots",
        arguments = {"doctor_id": doctor_id, "urgency": urgency},
    )
    t0 = time.perf_counter()
    try:
        result = get_slots(doctor_id, urgency)
        log_tool_result(call_id=call_id, tool_name="tool_get_slots", result=result, success=True, duration_ms=(time.perf_counter()-t0)*1000)
        return json.dumps(result)
    except Exception as exc:
        log_tool_result(call_id=call_id, tool_name="tool_get_slots", result={}, success=False, error=str(exc))
        raise


# ── Tool 4: book_slot ─────────────────────────────────────────────────────────

@mcp.tool()
def tool_book_slot(doctor_id: str, slot_key: str, patient_id: str, symptoms: str) -> str:
    user_id = f"USER-{patient_id}" if patient_id else None
    call_id = log_tool_call(
        tool_name  = "tool_book_slot",
        arguments  = {"doctor_id": doctor_id, "slot_key": slot_key, "patient_id": patient_id, "symptoms": symptoms},
        user_id    = user_id,
        patient_id = patient_id,
    )
    t0 = time.perf_counter()
    try:
        result = book_slot(doctor_id, slot_key, patient_id, symptoms)
        log_tool_result(call_id=call_id, tool_name="tool_book_slot", result=result, success=True, duration_ms=(time.perf_counter()-t0)*1000)
        return json.dumps(result)
    except Exception as exc:
        log_tool_result(call_id=call_id, tool_name="tool_book_slot", result={}, success=False, error=str(exc))
        raise


# ── Tool 5: cancel_appointment ────────────────────────────────────────────────

@mcp.tool()
def tool_cancel_appointment(booking_ref: str) -> str:
    call_id = log_tool_call(
        tool_name = "tool_cancel_appointment",
        arguments = {"booking_ref": booking_ref},
    )
    t0 = time.perf_counter()
    try:
        result = cancel_appointment(booking_ref)
        log_tool_result(call_id=call_id, tool_name="tool_cancel_appointment", result=result, success=True, duration_ms=(time.perf_counter()-t0)*1000)
        return json.dumps(result)
    except Exception as exc:
        log_tool_result(call_id=call_id, tool_name="tool_cancel_appointment", result={}, success=False, error=str(exc))
        raise

# ── Tool 8: get patient appointment history ──────────────────────────────────

@mcp.tool()
def tool_get_appointment_history(patient_id: str) -> str:
    user_id = f"USER-{patient_id}" if patient_id else None
    call_id = log_tool_call(
        tool_name  = "tool_get_appointment_history",
        arguments  = {"patient_id": patient_id},
        user_id    = user_id,
        patient_id = patient_id or None,
    )
    t0 = time.perf_counter()
    try:
        result = get_appointment_history(patient_id)
        log_tool_result(
            call_id=call_id,
            tool_name="tool_get_appointment_history",
            result=result,
            success=True,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        return json.dumps(result)
    except Exception as exc:
        log_tool_result(
            call_id=call_id,
            tool_name="tool_get_appointment_history",
            result={},
            success=False,
            error=str(exc),
        )
        raise


# ── Tool 9: get patient medical records ──────────────────────────────────────

# @mcp.tool()
# def tool_get_medical_records(patient_id: str) -> str:
#     user_id = f"USER-{patient_id}" if patient_id else None
#     call_id = log_tool_call(
#         tool_name  = "tool_get_medical_records",
#         arguments  = {"patient_id": patient_id},
#         user_id    = user_id,
#         patient_id = patient_id or None,
#     )
#     t0 = time.perf_counter()
#     try:
#         result = get_medical_records(patient_id)
#         log_tool_result(
#             call_id=call_id,
#             tool_name="tool_get_medical_records",
#             result=result,
#             success=True,
#             duration_ms=(time.perf_counter() - t0) * 1000,
#         )
#         return json.dumps(result)
#     except Exception as exc:
#         log_tool_result(
#             call_id=call_id,
#             tool_name="tool_get_medical_records",
#             result={},
#             success=False,
#             error=str(exc),
#         )
#         raise




# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading model into GPU memory...", file=sys.stderr)
    _load_model()
    print("Model ready. Starting server.", file=sys.stderr)
    mcp.run(transport="streamable-http")
