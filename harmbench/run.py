# harmbench/run.py — entry point
#
# Usage:
#   python -m harmbench.run                  # all behaviors, all attacks
#   python -m harmbench.run --category phi_extraction
#   python -m harmbench.run --behavior PI-001
#   python -m harmbench.run --no-report      # skip saving JSON report

import argparse
import asyncio
import json
from datetime import datetime
from mcp_client import call_tool

from harmbench.behaviors import BEHAVIORS
from harmbench.attacks   import ATTACKS
from harmbench.runner    import run_evaluation
from harmbench.report    import print_summary, save_report


def parse_args():
    p = argparse.ArgumentParser(description="Run HealthAgent HarmBench evaluation")
    p.add_argument("--category",  help="Filter to one category (e.g. phi_extraction)")
    p.add_argument("--behavior",  help="Filter to one behavior ID (e.g. PI-001)")
    p.add_argument("--attack",    help="Filter to one attack strategy (e.g. Roleplay)")
    p.add_argument("--no-report", action="store_true", help="Skip saving JSON report")
    return p.parse_args()


async def main():
    args = parse_args()

    behaviors = BEHAVIORS
    if args.category:
        behaviors = [b for b in behaviors if b.category == args.category]
    if args.behavior:
        behaviors = [b for b in behaviors if b.behavior_id == args.behavior]

    attacks = ATTACKS
    if args.attack:
        attacks = {k: v for k, v in attacks.items() if k == args.attack}

    if not behaviors:
        print("No behaviors matched the filter. Check --category / --behavior.")
        return
    if not attacks:
        print("No attacks matched. Available:", list(ATTACKS.keys()))
        return

    print("  Loading model...")
    await call_tool("tool_react_decide", {
        "messages_json": json.dumps([{"role": "user", "content": "hello"}]),
        "tools_json":    json.dumps([]),
    })
    print("  Model ready.\n")

    results = await run_evaluation(behaviors=behaviors, attacks=attacks)

    print_summary(results)

    if not args.no_report:
        path = save_report(results)
        print(f"\n  Report saved → {path}")



if __name__ == "__main__":
    asyncio.run(main())