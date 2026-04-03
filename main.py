# main.py — CLI entry point
#
# Now much simpler: collect patient identity, then hand everything
# off to run_agent(). MedGemma decides whether to book, cancel,
# ask questions, or do something else entirely.
#
# Run with:  python main.py
# Requires:  pip install httpx
#            Ollama running with alibayram/medgemma:4b pulled
#            MCP server running: python mcp_server.py
#            Healthcare.csv in the same folder

import asyncio

from agent    import run_agent
from database import init_db, get_patient, create_patient
from rag      import fetch_patient_context


async def main() -> None:
    _banner()
    init_db()

    # ── Identify patient ──────────────────────────────────────────────────
    print()
    patient_id = input("Your Patient ID (e.g. PT-00042, or press Enter to skip): ").strip().upper()

    patient_context = ""
    if patient_id:
        patient = get_patient(patient_id)

        if patient:
            print(f"\n  [DB] Found: {patient['name']} | {patient['age']} yrs, "
                  f"{patient['gender']} | {patient['disease']}")
            patient_context = fetch_patient_context(patient_id)
            print(f"  [RAG] Context loaded — {len(patient_context)} chars")
        else:
            print(f"  [DB] Patient '{patient_id}' not found — registering.")
            name    = input("  Full name              : ").strip() or "Anonymous"
            age_str = input("  Age                    : ").strip()
            age     = int(age_str) if age_str.isdigit() else 0
            gender  = input("  Gender (Male/Female/Other): ").strip() or "Other"
            create_patient(patient_id, name, age, gender, symptoms="")
            print(f"  [DB] Registered as {patient_id}.")

    # ── Single open-ended prompt — agent decides what to do ───────────────
    print()
    user_message = input("How can we help you today? ").strip()
    if not user_message:
        print("Nothing entered. Exiting.")
        return

    await run_agent(
        user_message    = user_message,
        patient_id      = patient_id,
        patient_context = patient_context,
    )


def _banner() -> None:
    print()
    print("  " + "─" * 51)
    print("           HEALTHAGENT — Terminal Version         ")
    print("  " + "─" * 51)
    print()


if __name__ == "__main__":
    asyncio.run(main())