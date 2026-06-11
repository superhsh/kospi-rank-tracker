"""
run_ribbon_screener.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
한국 · 미국 · 코인 전체를 스캔해 HMA(55) 기울기 전환 종목을
data/ribbon_screener.json 으로 저장합니다.

실행:
    python run_ribbon_screener.py
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.ribbon_screener import run_full_scan

if __name__ == "__main__":
    run_full_scan()
