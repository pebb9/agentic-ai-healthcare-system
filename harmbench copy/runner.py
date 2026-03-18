# harmbench/runner.py — evaluation orchestrator
#
# Routes each (behavior × attack) combination to the correct agent entry
# point, collects responses, and passes them to the judge.

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from harmbench.attacks   import ATTACKS
from harmbench.behaviors import Behavior, BEHAVIORS
from harmbench.judge     import judge

# Import agent tools directly so we can call them programmatically
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools import assess_symptoms, get_advice
from rag   import build_full_context
from config import DB_FILE

# The patient whose record is injected into PHI and prompt-injection tests
RAG_TEST_PATIENT_ID = "PT-00042"

# Categories that require patient context to be injected before the call
_CONTEXT_REQUIRED = {"phi_extraction", "prompt_injection"}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class TestResult:
    behavior_id:  str
    category:     str
    entry_point:  str
    attack:       str
    prompt:       str
    response:     str
    is_harmful:   bool
    judge_reason: str
    duration_ms:  float


# ── Target routing ────────────────────────────────────────────────────────────

async def _run_target(behavior: Behavior, attacked_prompt: str) -> str:
    """
    Route an attacked prompt to the correct agent entry point.

    PHI and prompt-injection categories receive full RAG context so the LLM
    has real patient data in its prompt — making attacks genuinely dangerous
    rather than theoretical.
    """
    patient_context = ""
    if behavior.category in _CONTEXT_REQUIRED:
        patient_context = build_full_context(RAG_TEST_PATIENT_ID, nearby_n=3)

    if behavior.entry_point == "tool_assess_symptoms":
        result = await assess_symptoms(attacked_prompt,
                                       patient_context=patient_context)
        return json.dumps(result)

    if behavior.entry_point == "tool_get_advice":
        result = await get_advice(attacked_prompt, "medium",
                                  patient_context=patient_context)
        return json.dumps(result)

    if behavior.entry_point == "patient_id_input":
        return _test_sql_injection(attacked_prompt)

    return "[no target matched]"


def _test_sql_injection(patient_id_input: str) -> str:
    """
    Compare the result of a parameterized query (safe) against raw string
    interpolation (unsafe) to detect whether injection would succeed.
    """
    if not os.path.exists(DB_FILE):
        return "[DB not found — run main.py first to initialise]"

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    # Parameterized — what the code actually does
    try:
        row          = conn.execute(
            "SELECT patient_id, name FROM patients WHERE patient_id = ?",
            (patient_id_input.upper(),),
        ).fetchone()
        safe_result  = dict(row) if row else "no match"
    except Exception as exc:
        safe_result  = f"ERROR: {exc}"

    # Raw interpolation — demonstrates what would happen if unprotected
    try:
        rows          = conn.execute(
            f"SELECT patient_id, name FROM patients "
            f"WHERE patient_id = '{patient_id_input.upper()}'"
        ).fetchall()
        unsafe_result = [dict(r) for r in rows] if rows else "no match"
    except Exception as exc:
        unsafe_result = f"ERROR: {exc}"

    conn.close()

    return json.dumps({
        "parameterized_query_result":  safe_result,
        "unsafe_interpolation_result": unsafe_result,
        "injection_would_succeed":     safe_result != unsafe_result,
    })


# ── Evaluation loop ───────────────────────────────────────────────────────────

async def run_evaluation(
    behaviors: list[Behavior] = BEHAVIORS,
    attacks:   dict           = ATTACKS,
    verbose:   bool           = True,
) -> list[TestResult]:
    """
    Run every (behavior × attack) combination and return a list of TestResults.
    """
    results: list[TestResult] = []
    total = len(behaviors) * len(attacks)
    done  = 0

    if verbose:
        print(f"\n{'='*60}")
        print(f"  HARMBENCH EVALUATION — HealthAgent")
        print(f"  RAG context patient : {RAG_TEST_PATIENT_ID}")
        print(f"  Test cases          : {len(behaviors)} behaviors × "
              f"{len(attacks)} attacks = {total}")
        print(f"{'='*60}\n")

    for behavior in behaviors:
        for attack_name, attack_fn in attacks.items():
            done += 1
            attacked_prompt = attack_fn(behavior.prompt)

            if verbose:
                print(
                    f"[{done:02d}/{total}] {behavior.behavior_id} "
                    f"× {attack_name:<15} ",
                    end="", flush=True,
                )

            t0 = datetime.now()
            try:
                response = await _run_target(behavior, attacked_prompt)
            except Exception as exc:
                response = f"[AGENT ERROR: {exc}]"
            duration_ms = (datetime.now() - t0).total_seconds() * 1000

            is_harmful, reason = judge(response, behavior)

            if verbose:
                status = "🔴 HARMFUL" if is_harmful else "🟢 safe"
                print(f"{status}  ({duration_ms:.0f}ms)")
                if is_harmful:
                    print(f"         Reason : {reason}")

            results.append(TestResult(
                behavior_id  = behavior.behavior_id,
                category     = behavior.category,
                entry_point  = behavior.entry_point,
                attack       = attack_name,
                prompt       = (attacked_prompt[:120] + "..."
                                if len(attacked_prompt) > 120
                                else attacked_prompt),
                response     = (response[:300] + "..."
                                if len(response) > 300
                                else response),
                is_harmful   = is_harmful,
                judge_reason = reason,
                duration_ms  = duration_ms,
            ))

    return results
