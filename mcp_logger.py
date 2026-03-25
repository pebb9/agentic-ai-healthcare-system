import json
import logging
import os
import sys
from datetime import datetime, timezone

LOGS_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
JSONL_FILE  = os.path.join(LOGS_DIR, "mcp_calls.jsonl")
TEXT_FILE   = os.path.join(LOGS_DIR, "mcp_calls.log")

os.makedirs(LOGS_DIR, exist_ok=True)

# Text logger — human readable
_text_logger = logging.getLogger("mcp_audit")  # Creates a new logger named "mcp_audit"
_text_logger.setLevel(logging.INFO) # Setting logging level to INFO (captures tool calls, results and session events)

if not _text_logger.handlers: # Checks if handlers are already added to avoid duplicate logs
    # File handler — persists to disk
    _fh = logging.FileHandler(TEXT_FILE, encoding="utf-8") # Creates a handler that writes to the file - logs are saved in UTF8
    _fh.setLevel(logging.INFO) # Same as above
    _fh.setFormatter(logging.Formatter(  # Defines format
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _text_logger.addHandler(_fh)

    # Console handler — prints to stderr (standard error) so it doesn't interfer with MCPs usage of stdout
    _sh = logging.StreamHandler(sys.stderr)
    _sh.setLevel(logging.INFO)
    _sh.setFormatter(logging.Formatter("  [AUDIT] %(message)s"))
    _text_logger.addHandler(_sh)


# Core logging functions

def log_tool_call(tool_name: str, arguments: dict, patient_id: str | None = None, session_id: str | None = None) -> str:
    call_id = _make_call_id() # making a unique ID for the tool call
    ts      = _now() # Timestamp now
  
    record = {
        "event":      "tool_call",
        "call_id":    call_id,
        "timestamp":  ts,
        "tool_name":  tool_name,
        "arguments":  arguments,
        "patient_id": patient_id,
        "session_id": session_id,
    }

    _write_jsonl(record)
    _text_logger.info(
        f"CALL  {tool_name:<30}  call_id={call_id}"
        + (f"  patient={patient_id}" if patient_id else "")
    )

    return call_id


def log_tool_result(call_id: str, tool_name: str, result: dict | str, success: bool = True, error: str | None = None, duration_ms: float | None = None,) -> None:
    ts = _now()

    record = {
        "event":       "tool_result",
        "call_id":     call_id,
        "timestamp":   ts,
        "tool_name":   tool_name,
        "success":     success,
        "error":       error,
        "duration_ms": round(duration_ms, 1) if duration_ms else None,
        "result":      result,
    }

    _write_jsonl(record)

    if success:
        _text_logger.info(f"RESULT {tool_name:<29}  call_id={call_id}")
        
    else:
        _text_logger.error(
            f"ERROR  {tool_name:<29}  call_id={call_id}  error={error}"
        )

def log_session_start(session_id: str, patient_id: str | None = None) -> None:

    record = {
        "event":      "session_start",
        "session_id": session_id,
        "timestamp":  _now(),
        "patient_id": patient_id,
    }
    _write_jsonl(record)
    _text_logger.info(f"SESSION START  session_id={session_id}" + (f"  patient={patient_id}" if patient_id else ""))

def log_session_end(session_id: str, patient_id: str | None = None) -> None:

    record = {
        "event":      "session_end",
        "session_id": session_id,
        "timestamp":  _now(),
        "patient_id": patient_id,
    }
    _write_jsonl(record)
    _text_logger.info(f"SESSION END    session_id={session_id}" + (f"  patient={patient_id}" if patient_id else "")
    )

# Internal helpers 

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_call_id() -> str:
    import uuid
    return str(uuid.uuid4())[:8]


def _write_jsonl(record: dict) -> None:
    with open(JSONL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")