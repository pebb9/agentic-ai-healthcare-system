# harmbench/run.py — HarmBench evaluation entry point
#
# Run with:  python -m harmbench.run
#        or: python harmbench/run.py

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database         import init_db
from harmbench.runner import run_evaluation
from harmbench.report import print_report


async def main() -> None:
    print("Initialising database...")
    init_db()

    results = await run_evaluation(verbose=True)
    print_report(results)


if __name__ == "__main__":
    asyncio.run(main())
