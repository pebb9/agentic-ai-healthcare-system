# harmbench/report.py — summary printing and JSON report saving

import json
from collections import defaultdict
from datetime import datetime

from harmbench.runner import TestResult


def print_summary(results: list[TestResult]) -> None:
    """Print ASR per category and overall to stdout."""

    by_category: dict[str, list[TestResult]] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)

    print()
    print("=" * 65)
    print("  RESULTS — Attack Success Rate (ASR) per category")
    print("=" * 65)

    total_harmful = 0
    for category, group in sorted(by_category.items()):
        harmful = sum(1 for r in group if r.is_harmful)
        total   = len(group)
        asr     = harmful / total * 100
        total_harmful += harmful
        bar = "#" * harmful + "-" * (total - harmful)
        print(f"  {category:<25}  {bar:<20}  {harmful}/{total}  ASR={asr:.0f}%")

    print("-" * 65)
    overall_asr = total_harmful / len(results) * 100 if results else 0
    print(f"  {'OVERALL':<25}  {total_harmful}/{len(results)}  ASR={overall_asr:.0f}%")
    print("=" * 65)

    # Print harmful cases detail
    harmful_cases = [r for r in results if r.is_harmful]
    if harmful_cases:
        print(f"\n  Harmful cases ({len(harmful_cases)}):\n")
        for r in harmful_cases:
            print(f"    {r.behavior_id} × {r.attack}")
            print(f"    Reason  : {r.judge_reason}")
            print(f"    Prompt  : {r.prompt[:80]}...")
            print(f"    Response: {r.response[:120]}...")
            print()
    else:
        print("\n  No harmful cases detected.")


def save_report(results: list[TestResult], path: str = None) -> str:
    """Save full results to a timestamped JSON file."""
    if path is None:
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"harmbench_report_{ts}.json"

    payload = {
        "generated_at": datetime.now().isoformat(),
        "total_cases":  len(results),
        "total_harmful": sum(1 for r in results if r.is_harmful),
        "overall_asr":  sum(1 for r in results if r.is_harmful) / len(results) if results else 0,
        "results": [
            {
                "behavior_id":  r.behavior_id,
                "category":     r.category,
                "entry_point":  r.entry_point,
                "attack":       r.attack,
                "is_harmful":   r.is_harmful,
                "judge_reason": r.judge_reason,
                "duration_ms":  round(r.duration_ms, 1),
                "prompt":       r.prompt,
                "response":     r.response,
            }
            for r in results
        ],
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return path