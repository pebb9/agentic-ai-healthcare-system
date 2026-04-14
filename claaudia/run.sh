#!/bin/bash
set -e

cd /scratch/app

echo -e "\nInstalling python requirements\n"
pip install --no-cache-dir -r requirements.txt

echo -e "\nStarting MCP server\n"
python3 mcp_server.py &
MCP_PID=$!

# Little sleep to let mcp_server start up properly before running main app
sleep 7

echo -e "\nRunning app\n"
python3 evaluation/triage_eval.py --limit 1

# Clean MCP server after main app finishes
kill $MCP_PID
