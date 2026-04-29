"""
run_daily.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
매 영업일 GitHub Actions에서 자동 실행되는 메인 스크립트입니다.
1. 오늘 날짜의 KOSPI/KOSDAQ 시총 데이터 수집
2. 일/주/월 순위 변동 계산
3. index.html 재생성

수동 실행:
    python run_daily.py
    python run_daily.py --date 20250425   # 특정 날짜 지정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import os
import sys
import time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher import (
    fetch_market_cap_krx,
    load_name_cache,
    save_market_data,
    save_name_cache,
)
from scripts.processor import build_report_data
from scripts.reporter import generate_html

MARKETS = ["KOSPI", "KOSDAQ"]


def parse_args():
    parser = argparse.ArgumentParser(description="일별 데이터 수집 및 리포트 생성")
    parser.add_argument("--date", type=str, default=None,
                        help="수집 날짜 YYYYMMDD (기본: 오늘)")
    return parser.parse_args()


def is_weekday(date_str: str) -> bool:
    """주말 여부 확인 (True = 평일)"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    return dt.weekday() < 5


def main():
    args    = parse_args()
    today   = args.date or datetime.today().strftime("%Y%m%d")

    print(f"\n{'='*50}")
    print(f"  일별 업데이트 시작 — {today}")
    print(f"{'='*50}\n")

    # 주말이면 실행 스킵 (GitHub Actions cron이 주말을 포함할 경우 대비)
    if not is_weekday(today):
        print(f"  ⚠ {today}은 주말입니다. 실행 스킵.")
        sys.exit(0)

    name_cache = load_name_cache()
    fetched_count = 0

    for market in MARKETS:
        print(f"  [{market}] 데이터 수집 중...")
        df = fetch_market_cap_krx(today, market, name_cache)

        if df.empty:
            print(f"  [{market}] ⚠ 데이터 없음 — 휴장일이거나 API 오류일 수 있습니다.")
        else:
            filepath = save_market_data(today, market, df)
            print(f"  [{market}] ✓ {len(df)}개 종목 저장 → {os.path.basename(filepath)}")
            fetched_count += 1
            time.sleep(1.0)  # 과도한 API 요청 방지

    # 종목명 캐시 저장
    save_name_cache(name_cache)

    if fetched_count == 0:
        print("\n  ⚠ 수집된 데이터가 없어 리포트를 생성하지 않습니다.")
        print("  (장 마감 전 실행이거나 공휴일일 수 있습니다.)\n")
        sys.exit(0)

    # 순위 변동 계산 및 HTML 생성
    print("\n  순위 변동 분석 중...")
    report_data = build_report_data(today)

    print("  HTML 리포트 생성 중...")
    html_path = generate_html(report_data)

    print(f"\n{'='*50}")
    print(f"  완료! → {html_path}")
    print(f"  KOSPI  일별 Top5: {len(report_data['kospi']['daily']['top5'])}개")
    print(f"  KOSPI  주별 Top5: {len(report_data['kospi']['weekly']['top5'])}개")
    print(f"  KOSPI  월별 Top5: {len(report_data['kospi']['monthly']['top5'])}개")
    print(f"  KOSDAQ 일별 Top5: {len(report_data['kosdaq']['daily']['top5'])}개")
    print(f"  KOSDAQ 주별 Top5: {len(report_data['kosdaq']['weekly']['top5'])}개")
    print(f"  KOSDAQ 월별 Top5: {len(report_data['kosdaq']['monthly']['top5'])}개")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
