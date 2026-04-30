"""
run_hourly.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
장중 시간별 순위 변동 업데이트 스크립트 (GitHub Actions 자동 실행)

실행 스케줄 (KST):
  09:20  →  전날 종가 대비 순위 변동
  11:00  →  09:20 스냅샷 대비 순위 변동
  13:00  →  11:00 스냅샷 대비 순위 변동
  15:00  →  13:00 스냅샷 대비 순위 변동

수동 실행:
  python run_hourly.py               # 현재 KST 시각 자동 판단
  python run_hourly.py --label 0920  # 라벨 직접 지정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher import (
    fetch_market_cap_krx,
    get_available_dates,
    load_market_data,
    load_name_cache,
    save_name_cache,
)
from scripts.intraday import (
    compute_top5,
    load_intraday,
    resolve_comparison,
    save_intraday,
)
from scripts.processor import build_report_data
from scripts.reporter import generate_html

KST    = timezone(timedelta(hours=9))
MARKETS = ["KOSPI", "KOSDAQ"]

# 라벨 → 표시용 시각
LABEL_DISPLAY = {
    "0920": "09:20",
    "1100": "11:00",
    "1300": "13:00",
    "1500": "15:00",
}


def detect_label() -> str | None:
    """현재 KST 시각에 해당하는 실행 라벨을 반환합니다.

    GitHub Actions cron 은 수십 분 지연될 수 있으므로,
    각 라벨의 유효 시간대를 넓게 잡습니다.
      0920 : 09:20 ~ 10:59
      1100 : 11:00 ~ 12:59
      1300 : 13:00 ~ 14:59
      1500 : 15:00 ~ 15:45
    """
    now   = datetime.now(KST)
    total = now.hour * 60 + now.minute   # 분 단위

    if 9 * 60 + 20 <= total < 11 * 60:  return "0920"
    if 11 * 60     <= total < 13 * 60:  return "1100"
    if 13 * 60     <= total < 15 * 60:  return "1300"
    if 15 * 60     <= total < 15 * 60 + 46: return "1500"
    return None


def parse_args():
    p = argparse.ArgumentParser(description="장중 순위 변동 업데이트")
    p.add_argument("--label", type=str, default=None,
                   choices=["0920", "1100", "1300", "1500"],
                   help="실행 라벨 (미지정 시 현재 KST 시각 기준 자동 판단)")
    return p.parse_args()


def main():
    args  = parse_args()
    label = args.label or detect_label()

    if not label:
        now_str = datetime.now(KST).strftime("%H:%M")
        print(f"현재 {now_str} KST 는 장중 업데이트 시간이 아닙니다.")
        print("실행 시각: 09:20 / 11:00 / 13:00 / 15:00 KST")
        sys.exit(0)

    today = datetime.now(KST).strftime("%Y%m%d")

    print(f"\n{'='*54}")
    print(f"  장중 업데이트 — {today}  {LABEL_DISPLAY[label]} KST")
    print(f"{'='*54}\n")

    name_cache   = load_name_cache()
    intraday_out = {}

    for market in MARKETS:
        print(f"  [{market}] 현재 시총 순위 수집 중...")
        current_df = fetch_market_cap_krx(today, market, name_cache)

        if current_df.empty:
            print(f"  [{market}] ⚠ 데이터 없음 (장 미개장 또는 공휴일)")
            intraday_out[market.lower()] = {
                "available": False, "top5": [],
                "label_display": LABEL_DISPLAY[label],
                "comparison": "데이터 없음",
            }
            continue

        # 현재 스냅샷 저장
        snap_path = save_intraday(market, today, label, current_df)
        print(f"  [{market}] ✓ {len(current_df)}개 종목 → {os.path.basename(snap_path)}")

        # 비교 대상 결정
        daily_dates = get_available_dates(market)
        source, prev_date, prev_label, comp_desc = resolve_comparison(
            market, today, label, daily_dates
        )

        if source == "daily":
            prev_df = load_market_data(prev_date, market)
        elif source == "intraday":
            prev_df = load_intraday(market, prev_date, prev_label)
        else:
            prev_df = pd.DataFrame()

        top5 = compute_top5(current_df, prev_df)
        print(f"  [{market}] 비교 기준: {comp_desc}  →  Top5 {len(top5)}개")

        intraday_out[market.lower()] = {
            "available":     True,
            "label":         label,
            "label_display": LABEL_DISPLAY[label],
            "comparison":    comp_desc,
            "top5":          top5,
        }

        time.sleep(0.5)

    save_name_cache(name_cache)

    # ── 일별·주별·월별 데이터도 포함해 통합 리포트 생성 ──────────────────────
    print("\n  전체 리포트 생성 중...")
    report_data = build_report_data(today)
    report_data["intraday"]   = intraday_out
    report_data["updated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M")

    generate_html(report_data)

    print(f"\n{'='*54}")
    print(f"  완료!  KOSPI  Top5: "
          f"{len(intraday_out.get('kospi',{}).get('top5',[]))}개")
    print(f"          KOSDAQ Top5: "
          f"{len(intraday_out.get('kosdaq',{}).get('top5',[]))}개")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
