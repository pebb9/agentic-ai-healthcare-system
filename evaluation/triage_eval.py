from pathlib import Path
import sys
import functools
print = functools.partial(print, flush=True)

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import argparse
import asyncio
import json
import ast

import pandas as pd

USE_MOCK = False

if not USE_MOCK:
    from mcp_client import call_tool
else:
    async def call_tool(tool_name: str, arguments: dict):
        if tool_name == "tool_react_decide":
            return {
                "action": "call_tool",
                "tool": "tool_assess_symptoms",
                "args": {
                    "symptoms": "mock symptoms"
                }
            }

        if tool_name == "tool_assess_symptoms":
            return {
                "urgency": "HIGH",
                "raw_llm_response": "Likely condition: Pneumonia. Triage level: HIGH."
            }

        return {
            "message": f"Mock result for {tool_name}"
        }


DEFAULT_DATASET = "healthcare_with_triage.csv"
DEFAULT_OUTPUT = "evaluation/results/triage_results.csv"


def parse_args():
    parser = argparse.ArgumentParser(description="Run triage benchmark against the health agent")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="Path to labeled CSV")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to save results CSV")
    parser.add_argument("--limit", type=int, default=None, help="Only run first N rows")
    parser.add_argument("--start", type=int, default=0, help="Start row index")
    return parser.parse_args()


async def warmup(max_retries=3):
    print("Waiting for MCP server...")

    for attempt in range(1, max_retries + 1):
        try:

            await call_tool(
                "tool_assess_symptoms",

                {
                    "symptoms": "mild headache",
                    "patient_id": "",
                    "patient_context": "",
                },
            )
            print("Model ready.")
            print("Warmup result:", result)
            return
        except Exception as exc:
            print(f"Server not ready yet, attempt {attempt}/{max_retries}: {exc}")
            await asyncio.sleep(5)

    raise RuntimeError("MCP server did not become ready")


def normalize_triage(value):
    if value is None:
        return None
    value = str(value).strip().upper()
    return value if value in {"LOW", "MEDIUM", "HIGH"} else None

def extract_prediction_from_text(text: str) -> dict:
    """
    Best-effort extraction from final natural-language response.
    """
    if not text:
        return {
            "predicted_disease": None,
            "predicted_triage": None,
            "reason": "Empty final response",
        }

    triage = None
    upper_text = text.upper()
    for level in ["HIGH", "MEDIUM", "LOW"]:
        if level in upper_text:
            triage = level
            break

    diseases = [
        "Common Cold", "Influenza", "COVID-19", "Pneumonia", "Tuberculosis",
        "Diabetes", "Hypertension", "Asthma", "Heart Disease",
        "Chronic Kidney Disease", "Gastritis", "Food Poisoning",
        "Irritable Bowel Syndrome (IBS)", "Liver Disease", "Ulcer",
        "Migraine", "Epilepsy", "Stroke", "Dementia", "Parkinson’s Disease",
        "Parkinson's Disease", "Allergy", "Arthritis", "Anemia",
        "Thyroid Disorder", "Obesity", "Depression", "Anxiety",
        "Dermatitis", "Sinusitis", "Bronchitis"
    ]

    predicted_disease = None
    lower_text = text.lower()
    for disease in diseases:
        if disease.lower() in lower_text:
            predicted_disease = disease
            break

    return {
        "predicted_disease": predicted_disease,
        "predicted_triage": triage,
        "reason": text,
    }

def extract_prediction_from_assessment_tool(tool_result: str) -> dict:
    """
    Parse tool_assess_symptoms result and extract benchmark fields.
    Expected shape is a JSON string like:
    {
        "urgency": "high",
        "doctors": [...],
        "raw_llm_response": "..."
    }
    """
    if not tool_result:
        return {
            "predicted_disease": None,
            "predicted_triage": None,
            "reason": "Empty tool result",
        }

    if isinstance(tool_result, dict):
        parsed = tool_result
    else:
        try:
            parsed = json.loads(tool_result)
        except Exception:
            try:
                parsed = ast.literal_eval(tool_result)
            except Exception:
                return {
                    "predicted_disease": None,
                    "predicted_triage": None,
                    "reason": f"Could not parse tool_assess_symptoms result: {tool_result}",
                }
<<<<<<< Updated upstream
    


=======
>>>>>>> Stashed changes

    urgency = str(parsed.get("urgency", "")).strip().upper()
    if urgency == "HIGH":
        triage = "HIGH"
    elif urgency == "MEDIUM":
        triage = "MEDIUM"
    elif urgency == "LOW":
        triage = "LOW"
    else:
        triage = None

    raw_text = parsed.get("raw_llm_response", "") or ""

    extracted = extract_prediction_from_text(raw_text)

    return {
        "predicted_disease": extracted.get("predicted_disease"),
        "predicted_triage": triage,
        "reason": raw_text if raw_text else str(parsed),
    }

def parse_agent_response(raw_response: str) -> dict:
    if not raw_response:
        return {
            "action": None,
            "message": None,
            "tool": None,
            "args": None,
            "predicted_disease": None,
            "predicted_triage": None,
            "reason": "Empty response",
            "raw_response": raw_response,
        }
    """
    Parse MCP responses that may be:
    - valid JSON
    - Python dict strings using single quotes
    """
    if isinstance(raw_response, dict):
        outer = raw_response
    else:
        outer = None


        try:
            outer = json.loads(raw_response)
        except Exception:
            pass

        if outer is None:
            try:
                outer = ast.literal_eval(raw_response)
            except Exception as exc:
                return {
                    "action": None,
                    "message": None,
                    "tool": None,
                    "args": None,
                    "predicted_disease": None,
                    "predicted_triage": None,
                    "reason": f"Could not parse MCP JSON/Python dict: {exc}",
                    "raw_response": raw_response,
                }

    if not isinstance(outer, dict):
        return {
            "action": None,
            "message": None,
            "tool": None,
            "args": None,
            "predicted_disease": None,
            "predicted_triage": None,
            "reason": f"Unexpected response format: {type(outer).__name__}",
            "raw_response": raw_response,
        }

    return {
        "action": outer.get("action"),
        "message": outer.get("message"),
        "tool": outer.get("tool"),
        "args": outer.get("args"),
        "predicted_disease": outer.get("predicted_disease"),
        "predicted_triage": normalize_triage(outer.get("predicted_triage")),
        "reason": outer.get("reason"),
        "raw_response": raw_response,
    }

async def query_agent(row: pd.Series) -> dict:
    try:
        symptoms_text = (
            f"I am {row['Age']} years old, {row['Gender']}. "
            f"My symptoms are: {row['Symptoms']}"
        )

        tool_result = await call_tool(
            "tool_assess_symptoms",
            {
                "symptoms": symptoms_text,
                "patient_id": "",
                "patient_context": "",
            },
        )

<<<<<<< Updated upstream
      
=======
        print("TOOL RESULT tool_assess_symptoms:", tool_result)
>>>>>>> Stashed changes

        extracted = extract_prediction_from_assessment_tool(tool_result)

<<<<<<< Updated upstream
        action = parsed.get("action")

        if action == "ask_user":
            agent_message = parsed.get("message", "")
            messages.append({"role": "assistant", "content": agent_message})

            if not symptoms_sent:
                user_reply = (
                    f"I am {row['Age']} years old, {row['Gender']}, "
                    f"and I have these symptoms: {row['Symptoms']}."
                )
                symptoms_sent = True
            else:
                # If the agent keeps asking questions, answer conservatively once.
                user_reply = (
                    "Based on my current symptoms, please continue with your assessment "
                    "and tell me the most likely disease and triage level."
                )

            messages.append({"role": "user", "content": user_reply})
            continue

        if action == "call_tool":
            tool_name = parsed.get("tool")
            tool_args = parsed.get("args") or {}

            if not tool_name:
                return {
                    "predicted_disease": None,
                    "predicted_triage": None,
                    "reason": "Agent requested tool call without tool name",
                    "raw_response": raw_response,
                }

            try:
                tool_result = await call_tool(tool_name, tool_args)
            except Exception as exc:
                return {
                    "predicted_disease": None,
                    "predicted_triage": None,
                    "reason": f"Tool call failed: {tool_name} -> {exc}",
                    "raw_response": raw_response,
                }

            

            print(f"TOOL RESULT {tool_name}:", tool_result)
            

            # Benchmark stop-point: use tool_assess_symptoms as the medical assessment output
            if tool_name == "tool_assess_symptoms":
                extracted = extract_prediction_from_assessment_tool(tool_result)
                return {
                    "predicted_disease": extracted.get("predicted_disease"),
                    "predicted_triage": extracted.get("predicted_triage"),
                    "reason": extracted.get("reason"),
                    "raw_response": tool_result,
                }

            # For any other tool, keep looping
            messages.append({"role": "assistant", "content":json.dumps(raw_response)})
            messages.append(
                {
                    "role": "tool",
                    "content": f"{tool_name} returned: {tool_result}",
                }
            )
            continue

        if action == "respond":
            final_message = parsed.get("message", "")

            # Try to extract structured prediction from the final message
            extracted = extract_prediction_from_text(final_message)

            return {
                "predicted_disease": extracted.get("predicted_disease"),
                "predicted_triage": extracted.get("predicted_triage"),
                "reason": extracted.get("reason") or final_message,
                "raw_response": raw_response,
            }

        # Direct prediction shape fallback
        if parsed.get("predicted_disease") is not None or parsed.get("predicted_triage") is not None:
            return {
                "predicted_disease": parsed.get("predicted_disease"),
                "predicted_triage": parsed.get("predicted_triage"),
                "reason": parsed.get("reason"),
                "raw_response": raw_response,
            }
=======
        return {
            "predicted_disease": extracted.get("predicted_disease"),
            "predicted_triage": extracted.get("predicted_triage"),
            "reason": extracted.get("reason"),
            "raw_response": tool_result,
        }
>>>>>>> Stashed changes

    except Exception as exc:
        return {
            "predicted_disease": None,
            "predicted_triage": None,
            "reason": f"Tool call failed: {exc}",
            "raw_response": "",
        }

def compute_metrics(df: pd.DataFrame):
    disease_mask = df["predicted_disease"].notna()
    triage_mask = df["predicted_triage"].notna()

    disease_acc = (df.loc[disease_mask, "Disease"] == df.loc[disease_mask, "predicted_disease"]).mean()
    triage_acc = (df.loc[triage_mask, "true_triage"] == df.loc[triage_mask, "predicted_triage"]).mean()

    disease_acc = 0.0 if pd.isna(disease_acc) else float(disease_acc)
    triage_acc = 0.0 if pd.isna(triage_acc) else float(triage_acc)

    high_cases = df[df["true_triage"] == "HIGH"]
    high_recall = float((high_cases["predicted_triage"] == "HIGH").mean()) if len(high_cases) else 0.0

    predicted_high = df[df["predicted_triage"] == "HIGH"]
    false_high_rate = float((predicted_high["true_triage"] != "HIGH").mean()) if len(predicted_high) else 0.0

    print("=== TRIAGE BENCHMARK SUMMARY ===")
    print(f"Rows evaluated:     {len(df)}")
    print(f"Disease accuracy:   {disease_acc:.3f}")
    print(f"Triage accuracy:    {triage_acc:.3f}")
    print(f"HIGH recall:        {high_recall:.3f}")
    print(f"False HIGH rate:    {false_high_rate:.3f}")
    print(f"Unparsed rows:      {int(df['predicted_triage'].isna().sum())}")

    missed_high = high_cases[high_cases["predicted_triage"] != "HIGH"]
    if not missed_high.empty:
        print("\n=== MISSED HIGH CASES (first 10) ===")
        cols = ["Symptoms", "Disease", "true_triage", "predicted_disease", "predicted_triage", "reason"]
        print(missed_high[cols].head(10).to_string(index=False))


async def main():
    args = parse_args()

    dataset_path = Path(args.dataset)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    df = pd.read_csv(dataset_path)

    required_cols = {"Age", "Gender", "Symptoms", "Symptom_Count", "Disease", "true_triage"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")

    if args.start:
        df = df.iloc[args.start:]

    if args.limit is not None:
        df = df.head(args.limit)

    await warmup()

    results = []
    total = len(df)

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        print(f"[{idx}/{total}] Running case...")
        try:
            pred = await query_agent(row)
        except Exception as exc:
            pred = {
                "predicted_disease": None,
                "predicted_triage": None,
                "reason": f"Agent call failed: {exc}",
                "raw_response": "",
            }

        results.append(pred)

    results_df = pd.DataFrame(results)
    final_df = pd.concat([df.reset_index(drop=True), results_df], axis=1)

    compute_metrics(final_df)
    final_df.to_csv(output_path, index=False)

    print(f"\nSaved results to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
