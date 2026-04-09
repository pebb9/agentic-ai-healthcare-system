# harmbench2/run.py — entry point
#
# Run from the project root:
#   python -m harmbench2.run
#
# Prerequisites:
#   1. MCP server running:  python mcp_server.py
#   2. Ollama running:      ollama serve  (with medgemma:4b pulled)
#   3. DB initialised:      python main.py  (or let init_db() handle it)

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database          import init_db
from harmbench.runner import run_evaluation
from harmbench.report import print_report


async def main() -> None:
    print("Initialising database...")
    init_db()

    results = await run_evaluation(verbose=True)
    print_report(results)


if __name__ == "__main__":
    asyncio.run(main())