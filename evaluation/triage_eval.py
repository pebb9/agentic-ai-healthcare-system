from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import argparse
import asyncio
import json
from pathlib import Path

import pandas as pd

from mcp_client import call_tool


DEFAULT_DATASET = "data/healthcare_with_triage.csv"
DEFAULT_OUTPUT = "evaluation/results/triage_results.csv"


def parse_args():
    parser = argparse.ArgumentParser(description="Run triage benchmark against the health agent")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="Path to labeled CSV")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Path to save results CSV")
    parser.add_argument("--limit", type=int, default=None, help="Only run first N rows")
    parser.add_argument("--start", type=int, default=0, help="Start row index")
    return parser.parse_args()


def build_prompt(row: pd.Series) -> str:
    return (
        "You are evaluating a healthcare triage system.\n"
        "Given the patient data below, identify the most likely disease and assign a triage level.\n\n"
        f"Age: {row['Age']}\n"
        f"Gender: {row['Gender']}\n"
        f"Symptoms: {row['Symptoms']}\n"
        f"Symptom_Count: {row['Symptom_Count']}\n\n"
        "Return valid JSON only with exactly these keys:\n"
        '{'
        '"predicted_disease": "<disease name>", '
        '"predicted_triage": "LOW|MEDIUM|HIGH", '
        '"reason": "<short explanation>"'
        '}'
    )


async def warmup():
    print("Waiting for MCP server...")
    while True:
        try:
            await call_tool(
                "tool_react_decide",
                {
                    "messages_json": json.dumps([{"role": "user", "content": "hello"}]),
                    "tools_json": json.dumps([]),
                },
            )
            print("Model ready.\n")
            return
        except Exception as exc:
            print(f"Server not ready yet: {exc}")
            print("Retrying in 5 seconds...\n")
            await asyncio.sleep(5)


def normalize_triage(value):
    if value is None:
        return None
    value = str(value).strip().upper()
    return value if value in {"LOW", "MEDIUM", "HIGH"} else None


def parse_agent_response(raw_response: str) -> dict:
    """
    MCP server returns json.dumps(decision), so raw_response should be a JSON string.
    We parse that first, then try to extract predicted_disease / predicted_triage / reason.
    """
    if not raw_response:
        return {
            "predicted_disease": None,
            "predicted_triage": None,
            "reason": "Empty response",
            "raw_response": raw_response,
        }

    try:
        outer = json.loads(raw_response)
    except Exception as exc:
        return {
            "predicted_disease": None,
            "predicted_triage": None,
            "reason": f"Could not parse MCP JSON: {exc}",
            "raw_response": raw_response,
        }

    # Case 1: model already returned the desired dict directly
    if isinstance(outer, dict) and (
        "predicted_disease" in outer or "predicted_triage" in outer
    ):
        return {
            "predicted_disease": outer.get("predicted_disease"),
            "predicted_triage": normalize_triage(outer.get("predicted_triage")),
            "reason": outer.get("reason"),
            "raw_response": raw_response,
        }

    # Case 2: ReAct output wraps final answer in a field like content / answer / final
    candidate_fields = ["content", "answer", "final", "final_answer", "output", "text"]
    if isinstance(outer, dict):
        for field in candidate_fields:
            value = outer.get(field)
            if isinstance(value, str):
                try:
                    inner = json.loads(value)
                    if isinstance(inner, dict):
                        return {
                            "predicted_disease": inner.get("predicted_disease"),
                            "predicted_triage": normalize_triage(inner.get("predicted_triage")),
                            "reason": inner.get("reason"),
                            "raw_response": raw_response,
                        }
                except Exception:
                    continue

    # Case 3: fallback
    return {
        "predicted_disease": None,
        "predicted_triage": None,
        "reason": f"Unexpected response format: {type(outer).__name__}",
        "raw_response": raw_response,
    }


async def query_agent(row: pd.Series) -> dict:
    messages = [{"role": "user", "content": build_prompt(row)}]

    raw_response = await call_tool(
        "tool_react_decide",
        {
            "messages_json": json.dumps(messages),
            "tools_json": json.dumps([]),
        },
    )

    if not isinstance(raw_response, str):
        raw_response = str(raw_response)

    return parse_agent_response(raw_response)


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