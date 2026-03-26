# Run with:  python mcp_server.py
# Listens on: http://127.0.0.1:8000/mcp

import json
import sys
import time

from mcp.server.fastmcp import FastMCP

from tools import assess_symptoms, get_advice, get_slots, book_slot
from mcp_logger import log_tool_call, log_tool_result

mcp = FastMCP("healthagent", host="127.0.0.1", port=8000)

# Tool 1: assess_symptoms

@mcp.tool()
async def tool_assess_symptoms(symptoms: str, patient_context: str = "") -> str:
    call_id = log_tool_call(
        tool_name  = "tool_assess_symptoms",
        arguments  = {"symptoms": symptoms, "patient_context": patient_context})
    
    t0 = time.perf_counter()
    try:
        result = await assess_symptoms(symptoms, patient_context=patient_context)
        log_tool_result(
            call_id     = call_id,
            tool_name   = "tool_assess_symptoms",
            result      = result,
            success     = True,
            duration_ms = (time.perf_counter() - t0) * 1000,
        )
        return json.dumps(result)
    except Exception as exc:
        log_tool_result(
            call_id   = call_id,
            tool_name = "tool_assess_symptoms",
            result    = {},
            success   = False,
            error     = str(exc),
        )
        raise


# ── Tool 2: get_advice ────────────────────────────────────────────────────────

@mcp.tool()
async def tool_get_advice(symptoms: str, urgency: str, patient_context: str = "") -> str:
    
    call_id = log_tool_call(
        tool_name = "tool_get_advice",
        arguments = {"symptoms": symptoms, "urgency": urgency, "patient_context": patient_context})
    t0 = time.perf_counter()
    try:
        result = await get_advice(symptoms, urgency, patient_context=patient_context)
        log_tool_result(
            call_id     = call_id,
            tool_name   = "tool_get_advice",
            result      = result,
            success     = True,
            duration_ms = (time.perf_counter() - t0) * 1000,
        )
        return json.dumps(result)
    except Exception as exc:
        log_tool_result(
            call_id   = call_id,
            tool_name = "tool_get_advice",
            result    = {},
            success   = False,
            error     = str(exc),
        )
        raise


# Tool 3: get_slots

@mcp.tool()
def tool_get_slots(doctor_id: str, urgency: str) -> str:

    call_id = log_tool_call(
        tool_name = "tool_get_slots",
        arguments = {"doctor_id": doctor_id, "urgency": urgency},
    )
    t0 = time.perf_counter()
    try:
        result = get_slots(doctor_id, urgency)
        log_tool_result(
            call_id     = call_id,
            tool_name   = "tool_get_slots",
            result      = result,
            success     = True,
            duration_ms = (time.perf_counter() - t0) * 1000,
        )
        return json.dumps(result)
    except Exception as exc:
        log_tool_result(
            call_id   = call_id,
            tool_name = "tool_get_slots",
            result    = {},
            success   = False,
            error     = str(exc),
        )
        raise


# Tool 4: book_slot

@mcp.tool()
def tool_book_slot(doctor_id: str, slot_key: str, patient_id: str, symptoms: str) -> str:
    
    call_id = log_tool_call(
        tool_name  = "tool_book_slot",
        arguments  = {"doctor_id": doctor_id, "slot_key": slot_key, "patient_id": patient_id, "symptoms": symptoms}, patient_id = patient_id)
    t0 = time.perf_counter()
    try:
        result = book_slot(doctor_id, slot_key, patient_id, symptoms)
        log_tool_result(
            call_id     = call_id,
            tool_name   = "tool_book_slot",
            result      = result,
            success     = True,
            duration_ms = (time.perf_counter() - t0) * 1000,
        )
        return json.dumps(result)
    except Exception as exc:
        log_tool_result(
            call_id   = call_id,
            tool_name = "tool_book_slot",
            result    = {},
            success   = False,
            error     = str(exc),
        )
        raise

# Entry point 

if __name__ == "__main__":
    print("HealthAgent MCP server starting on http://127.0.0.1:8000/mcp",
          file=sys.stderr)
    print("Logs → logs/mcp_calls.jsonl  |  logs/mcp_calls.log",
          file=sys.stderr)
    mcp.run(transport="streamable-http")