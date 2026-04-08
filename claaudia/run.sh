#!/bin/bash
set -e

cd /scratch/app

echo -e "\nInstalling python requirements\n"
pip install --no-cache-dir -r requirements.txt

echo -e "\nRunning app\n"
python3 main.py
