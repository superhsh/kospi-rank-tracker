"""
run_daily.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
매 영업일 GitHub Actions에서 자동 실행되는 메인 스크립트입니다.
1. 오늘 날짜의 KOSPI/KOSDAQ 시총 데이터 수집
2. 일/주/월 순위 변동 계산
3. 오늘 저장된 장중 스냅샷이 있으면 장중 탭에도 포함
4. index.html 재생성

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

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher import (
    fetch_market_cap_krx,
    get_available_dates,
    load_market_data,
    load_name_cache,
    save_market_data,
    save_name_cache,
)
from scripts.history_builder import attach_histories, attach_intraday_history
from scripts.intraday import (
    compute_top5,
    get_saved_labels,
    load_intraday,
    resolve_comparison,
)
from scripts.processor import build_report_data
from scripts.reporter import generate_html

MARKETS = ["KOSPI", "KOSDAQ"]

LABEL_DISPLAY = {
    "0920": "09:20",
    "1100": "11:00",
    "1300": "13:00",
    "1500": "15:00",
}


def parse_args():
    parser = argparse.ArgumentParser(description="일별 데이터 수집 및 리포트 생성")
    parser.add_argument("--date", type=str, default=None,
                        help="수집 날짜 YYYYMMDD (기본: 오늘)")
    return parser.parse_args()


def is_weekday(date_str: str) -> bool:
    """주말 여부 확인 (True = 평일)"""
    dt = datetime.strptime(date_str, "%Y%m%d")
    return dt.weekday() < 5


def load_todays_intraday(today: str) -> dict:
    """
    오늘 저장된 장중 스냅샷 중 최신 라벨을 기준으로
    intraday_out 딕셔너리를 구성합니다.
    run_daily.py 실행 시 장중 탭에 데이터를 포함하기 위해 사용합니다.
    """
    intraday_out = {}

    for market in MARKETS:
        saved = get_saved_labels(market, today)
        if not saved:
            intraday_out[market.lower()] = {
                "available": False, "top5": [],
                "label_display": "-", "comparison": "오늘 장중 데이터 없음",
            }
            continue

        latest_label = saved[-1]
        current_df   = load_intraday(market, today, latest_label)

        if current_df.empty:
            intraday_out[market.lower()] = {
                "available": False, "top5": [],
                "label_display": LABEL_DISPLAY.get(latest_label, latest_label),
                "comparison": "스냅샷 로드 실패",
            }
            continue

        # 비교 기준 결정 (run_hourly.py와 동일한 로직)
        daily_dates = get_available_dates(market)
        source, prev_date, prev_label, comp_desc = resolve_comparison(
            market, today, latest_label, daily_dates
        )

        if source == "daily":
            prev_df = load_market_data(prev_date, market)
        elif source == "intraday":
            prev_df = load_intraday(market, prev_date, prev_label)
        else:
            prev_df = pd.DataFrame()

        top5 = compute_top5(current_df, prev_df)

        intraday_out[market.lower()] = {
            "available":     True,
            "label":         latest_label,
            "label_display": LABEL_DISPLAY.get(latest_label, latest_label),
            "comparison":    comp_desc,
            "top5":          top5,
        }

        print(f"  [{market}] 장중 스냅샷 로드 — {LABEL_DISPLAY.get(latest_label)} "
              f"({comp_desc}) Top5 {len(top5)}개")

    return intraday_out


def main():
    args  = parse_args()
    today = args.date or datetime.today().strftime("%Y%m%d")

    print(f"\n{'='*50}")
    print(f"  일별 업데이트 시작 — {today}")
    print(f"{'='*50}\n")

    if not is_weekday(today):
        print(f"  ⚠ {today}은 주말입니다. 실행 스킵.")
        sys.exit(0)

    name_cache    = load_name_cache()
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
            time.sleep(1.0)

    save_name_cache(name_cache)

    if fetched_count == 0:
        print("\n  ⚠ 수집된 데이터가 없어 리포트를 생성하지 않습니다.")
        sys.exit(0)

    # ── 일/주/월 순위 변동 계산 ────────────────────────────────────────────────
    print("\n  순위 변동 분석 중...")
    report_data = build_report_data(today)

    # ── 오늘 저장된 장중 스냅샷 포함 ──────────────────────────────────────────
    print("\n  오늘 장중 스냅샷 확인 중...")
    intraday_out = load_todays_intraday(today)
    report_data["intraday"] = intraday_out

    # ── 히스토리 계산 ─────────────────────────────────────────────────────────
    print("\n  히스토리 데이터 계산 중...")
    report_data = attach_histories(report_data, MARKETS, today)
    report_data = attach_intraday_history(report_data, MARKETS, today)

    report_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── HTML 생성 ─────────────────────────────────────────────────────────────
    print("\n  HTML 리포트 생성 중...")
    html_path = generate_html(report_data)

    has_intraday = any(
        v.get("available") for v in intraday_out.values()
    )
    print(f"\n{'='*50}")
    print(f"  완료! → {html_path}")
    print(f"  장중 데이터: {'포함' if has_intraday else '없음 (장 마감 후 첫 실행)'}")
    print(f"  KOSPI  일별 Top5: {len(report_data['kospi']['daily']['top5'])}개")
    print(f"  KOSPI  주별 Top5: {len(report_data['kospi']['weekly']['top5'])}개")
    print(f"  KOSPI  월별 Top5: {len(report_data['kospi']['monthly']['top5'])}개")
    print(f"  KOSDAQ 일별 Top5: {len(report_data['kosdaq']['daily']['top5'])}개")
    print(f"  KOSDAQ 주별 Top5: {len(report_data['kosdaq']['weekly']['top5'])}개")
    print(f"  KOSDAQ 월별 Top5: {len(report_data['kosdaq']['monthly']['top5'])}개")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
