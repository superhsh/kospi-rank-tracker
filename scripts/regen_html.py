"""
regen_html.py
기존 data/report.json(KR 데이터)을 읽어 index.html을 재생성합니다.
reporter.py 템플릿이 변경됐을 때 index.html을 최신 상태로 갱신하는 용도.
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from scripts.reporter import generate_html

kr_path = os.path.join(BASE_DIR, "data", "report.json")

if os.path.exists(kr_path):
    with open(kr_path, encoding="utf-8") as f:
        data = json.load(f)
    generate_html(data)
    print("index.html 재생성 완료")
else:
    print("data/report.json 없음 — index.html 재생성 스킵")
